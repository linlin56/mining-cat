# WaylandPortalCapture against a fake PyGObject (Gio / GLib / Gst / GstVideo), so it runs without a desktop portal.
import contextlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from game_ocr.capture import CaptureError
from game_ocr.capture import linux_wayland

W, H = 4, 2


class FakeBus:
    # `responses`: portal method -> (response code, results) sent back through the Request's Response signal.
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self._on_response = None

    def get_unique_name(self):
        return ":1.42"

    def signal_subscribe(self, _bus, _iface, _signal, path, _arg0, _flags, callback):
        self.subscribed_path = path
        self._on_response = callback
        return 1

    def signal_unsubscribe(self, _sub_id):
        self._on_response = None

    def call_sync(self, _bus, _obj, _iface, method, variant, *_rest):
        self.calls.append((method, variant))
        if method in self.responses:
            code, results = self.responses[method]
            self._on_response(None, None, None, None, None, SimpleNamespace(unpack=lambda: (code, results)))

    def call_with_unix_fd_list_sync(self, *_args):
        return SimpleNamespace(unpack=lambda: (0,)), SimpleNamespace(get=lambda _i: 11)


def _portal_responses(restore_token="token-2", streams=((42, {}),), start_code=0):
    return {
        "CreateSession": (0, {"session_handle": "/session/1"}),
        "SelectSources": (0, {}),
        "Start": (start_code, {"streams": list(streams), "restore_token": restore_token}),
    }


def _fake_gi(bus):
    Gio = MagicMock()
    Gio.bus_get_sync.return_value = bus
    GLib = MagicMock()
    GLib.Variant = lambda signature, value: (signature, value)
    GLib.Error = type("GLibError", (Exception,), {})
    Gst = MagicMock()
    Gst.SECOND = 1_000_000_000
    Gst.StateChangeReturn.FAILURE = "failure"
    Gst.parse_launch.return_value.set_state.return_value = "success"
    GstVideo = MagicMock()
    GstVideo.VideoInfo.new_from_caps.return_value = SimpleNamespace(width=W, height=H, stride=[W * 3])
    return Gio, GLib, Gst, GstVideo


@contextlib.contextmanager
def _fake_portal(responses=None):
    bus = FakeBus(responses if responses is not None else _portal_responses())
    modules = _fake_gi(bus)
    with patch.object(linux_wayland, "_import_gi", return_value=modules):
        yield bus, modules


def _options(bus, method):
    variant = next(v for m, v in bus.calls if m == method)
    return variant[1][-1]


def test_import_gi_missing_raises_install_hint():
    with patch.dict("sys.modules", {"gi": None}):
        with pytest.raises(CaptureError, match="gstreamer1.0-pipewire"):
            linux_wayland._import_gi()


def test_has_system_picker_and_cannot_list_windows():
    with _fake_portal():
        backend = linux_wayland.WaylandPortalCapture()
        assert backend.has_system_picker
        with pytest.raises(CaptureError):
            backend.list_windows()
        assert backend.window_label


def test_select_window_asks_the_portal_without_restore_token():
    with _fake_portal() as (bus, (_Gio, _GLib, Gst, _GstVideo)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.select_window()
    select = _options(bus, "SelectSources")
    assert "restore_token" not in select
    assert select["types"] == ("u", 2)
    assert select["persist_mode"] == ("u", 2)
    assert backend.state == {"restore_token": "token-2"}
    assert "pipewiresrc fd=11 path=42" in Gst.parse_launch.call_args[0][0]
    assert bus.subscribed_path.startswith("/org/freedesktop/portal/desktop/request/1_42/")


def test_restore_reuses_token_and_stores_the_new_single_use_one():
    with _fake_portal() as (bus, _modules):
        backend = linux_wayland.WaylandPortalCapture()
        backend.restore({"restore_token": "token-1"})
    assert _options(bus, "SelectSources")["restore_token"] == ("s", "token-1")
    assert backend.state == {"restore_token": "token-2"}


def test_restore_keeps_token_when_portal_returns_none():
    with _fake_portal(_portal_responses(restore_token=None)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.restore({"restore_token": "token-1"})
    assert backend.state == {"restore_token": "token-1"}


def test_restore_without_token_raises():
    with _fake_portal():
        with pytest.raises(CaptureError, match="select the window again"):
            linux_wayland.WaylandPortalCapture().restore({})


def test_restore_refused_by_portal_mentions_revoked_permission():
    with _fake_portal(_portal_responses(start_code=1)):
        with pytest.raises(CaptureError, match="revoked"):
            linux_wayland.WaylandPortalCapture().restore({"restore_token": "token-1"})


def test_select_window_cancelled_without_streams_raises():
    with _fake_portal(_portal_responses(streams=())):
        with pytest.raises(CaptureError, match="No window shared"):
            linux_wayland.WaylandPortalCapture().select_window()


def test_portal_timeout_raises():
    with _fake_portal({}):  # the portal never answers
        backend = linux_wayland.WaylandPortalCapture()
        with pytest.raises(CaptureError, match="timeout"):
            backend._request("CreateSession", ({},), timeout=0.01)


def test_pipeline_start_failure_raises():
    with _fake_portal() as (_bus, (_Gio, _GLib, Gst, _GstVideo)):
        Gst.parse_launch.return_value.set_state.return_value = "failure"
        with pytest.raises(CaptureError, match="pipeline"):
            linux_wayland.WaylandPortalCapture().select_window()


def test_grab_frame_before_selection_raises():
    with _fake_portal():
        with pytest.raises(CaptureError, match="No window selected"):
            linux_wayland.WaylandPortalCapture().grab_frame()


def test_grab_frame_converts_the_pipewire_sample():
    with _fake_portal() as (_bus, (_Gio, _GLib, Gst, _GstVideo)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.select_window()
        buffer = MagicMock()
        buffer.map.return_value = (True, SimpleNamespace(data=bytes([10, 20, 30]) * (W * H)))
        sample = MagicMock(**{"get_buffer.return_value": buffer})
        Gst.parse_launch.return_value.get_by_name.return_value.emit.return_value = sample
        image = backend.grab_frame()
    assert image.size == (W, H)
    assert image.getpixel((0, 0)) == (10, 20, 30)
    buffer.unmap.assert_called_once()


def test_grab_frame_timeout_raises():
    with _fake_portal() as (_bus, (_Gio, _GLib, Gst, _GstVideo)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.select_window()
        Gst.parse_launch.return_value.get_by_name.return_value.emit.return_value = None
        with pytest.raises(CaptureError, match="No frame received"):
            backend.grab_frame()


def test_grab_frame_buffer_map_failure_raises():
    with _fake_portal() as (_bus, (_Gio, _GLib, Gst, _GstVideo)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.select_window()
        buffer = MagicMock(**{"map.return_value": (False, None)})
        Gst.parse_launch.return_value.get_by_name.return_value.emit.return_value = MagicMock(**{"get_buffer.return_value": buffer})
        with pytest.raises(CaptureError, match="map"):
            backend.grab_frame()


def test_close_stops_pipeline_and_closes_session_even_if_dbus_fails():
    with _fake_portal() as (bus, (_Gio, GLib, Gst, _GstVideo)):
        backend = linux_wayland.WaylandPortalCapture()
        backend.select_window()
        bus.call_sync = MagicMock(side_effect=GLib.Error("gone"))
        backend.close()
        backend.close()  # idempotent
    Gst.parse_launch.return_value.set_state.assert_called_with(Gst.State.NULL)
    bus.call_sync.assert_called_once()
