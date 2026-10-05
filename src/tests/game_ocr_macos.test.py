# MacOSCapture against fake pyobjc modules (Quartz / ScreenCaptureKit / objc), so it runs on any OS.
import contextlib
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from game_ocr.capture import CaptureError, WindowInfo
from game_ocr.capture import macos

W, H = 4, 2
# BGRA pixels: pure blue (B=255) once converted to RGB
_BGRA_BLUE = bytes([255, 0, 0, 255]) * (W * H)


def _window_info(number, owner, name="", layer=0, pid=123, width=800, height=600):
    return {
        "kCGWindowNumber": number, "kCGWindowOwnerName": owner, "kCGWindowName": name,
        "kCGWindowLayer": layer, "kCGWindowOwnerPID": pid,
        "kCGWindowBounds": {"X": 0, "Y": 0, "Width": width, "Height": height},
    }


def _fake_quartz(windows, permission=True):
    q = MagicMock()
    q.CGPreflightScreenCaptureAccess.return_value = permission
    q.CGWindowListCopyWindowInfo.side_effect = lambda option, window_id: (
        windows if window_id == q.kCGNullWindowID else [w for w in windows if w["kCGWindowNumber"] == window_id]
    )
    q.CGImageGetWidth.return_value = W
    q.CGImageGetHeight.return_value = H
    q.CGImageGetBytesPerRow.return_value = W * 4
    q.CGDataProviderCopyData.return_value = _BGRA_BLUE
    return q


def _fake_sck(window_ids, image=object(), error=None):
    sck = MagicMock()
    content = MagicMock()
    content.windows.return_value = [MagicMock(**{"windowID.return_value": wid}) for wid in window_ids]
    sck.SCShareableContent.getShareableContentWithCompletionHandler_.side_effect = lambda handler: handler(content, None)
    sck.SCContentFilter.alloc.return_value.initWithDesktopIndependentWindow_.return_value.pointPixelScale.return_value = 2.0
    sck.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_.side_effect = (
        lambda _filter, _config, handler: handler(image, error)
    )
    return sck


@contextlib.contextmanager
def _macos_modules(quartz, sck=None):
    objc = SimpleNamespace(autorelease_pool=contextlib.nullcontext)
    modules = {"objc": objc, "Quartz": quartz, "ScreenCaptureKit": sck or MagicMock()}
    with patch.dict("sys.modules", modules):
        yield


GAME = _window_info(10, "Ryujinx", "Zelda")
WINDOWS = [
    GAME,
    _window_info(11, "Steam", ""),
    _window_info(12, "Menubar", layer=25),
    _window_info(13, "Tiny", width=20, height=20),
    _window_info(14, "Python", pid=os.getpid()),
]


# init
def test_before_macos_14_raises_capture_error():
    sck = SimpleNamespace()  # no SCScreenshotManager before macOS 14
    with _macos_modules(_fake_quartz(WINDOWS), sck):
        with pytest.raises(CaptureError, match="macOS 14"):
            macos.MacOSCapture()


def test_init_without_pyobjc_raises_capture_error():
    with patch.dict("sys.modules", {"objc": None, "Quartz": None}):
        with pytest.raises(CaptureError, match="pyobjc"):
            macos.MacOSCapture()






# list_windows
def test_list_windows_keeps_normal_windows_of_other_apps():
    with _macos_modules(_fake_quartz(WINDOWS)):
        windows = macos.MacOSCapture().list_windows()
    assert windows == [WindowInfo(10, "Ryujinx", "Zelda"), WindowInfo(11, "Steam", "")]


def test_list_windows_without_permission_asks_for_it():
    quartz = _fake_quartz(WINDOWS, permission=False)
    with _macos_modules(quartz):
        with pytest.raises(CaptureError, match="Screen Recording permission"):
            macos.MacOSCapture().list_windows()
    quartz.CGRequestScreenCaptureAccess.assert_called_once()


# select / restore / state
def test_select_window_requires_a_window():
    with _macos_modules(_fake_quartz(WINDOWS)):
        with pytest.raises(CaptureError):
            macos.MacOSCapture().select_window(None)


def test_state_and_label_follow_selected_window():
    with _macos_modules(_fake_quartz(WINDOWS)):
        backend = macos.MacOSCapture()
        assert backend.state == {} and backend.window_label == ""
        backend.select_window(WindowInfo(10, "Ryujinx", "Zelda"))
        assert backend.state == {"id": 10, "owner": "Ryujinx", "title": "Zelda"}
        assert backend.window_label == "Ryujinx - Zelda"


@pytest.mark.parametrize("state, expected_id", [
    ({"id": 10, "owner": "Ryujinx", "title": "Zelda"}, 10),        # same window id
    ({"id": 999, "owner": "Ryujinx", "title": "Zelda"}, 10),       # app restarted: same app + title
    ({"id": 999, "owner": "Steam", "title": "Old title"}, 11),     # title changed: same app
])
def test_restore_finds_the_saved_window(state, expected_id):
    with _macos_modules(_fake_quartz(WINDOWS)):
        backend = macos.MacOSCapture()
        backend.restore(state)
    assert backend.state["id"] == expected_id


def test_restore_window_not_found_raises():
    with _macos_modules(_fake_quartz(WINDOWS)):
        with pytest.raises(CaptureError, match="not found"):
            macos.MacOSCapture().restore({"id": 1, "owner": "Closed game"})


def test_restore_without_saved_window_raises():
    with _macos_modules(_fake_quartz(WINDOWS)):
        with pytest.raises(CaptureError, match="No window saved"):
            macos.MacOSCapture().restore({})


# grab_frame
def test_grab_frame_without_window_raises():
    with _macos_modules(_fake_quartz(WINDOWS)):
        with pytest.raises(CaptureError, match="No window selected"):
            macos.MacOSCapture().grab_frame()






def test_grab_frame_with_screencapturekit_uses_retina_size_and_caches_filter():
    quartz, sck = _fake_quartz(WINDOWS), _fake_sck([10, 11])
    with _macos_modules(quartz, sck):
        backend = macos.MacOSCapture()
        backend.select_window(WindowInfo(10, "Ryujinx", "Zelda"))
        assert backend.grab_frame().getpixel((0, 0)) == (0, 0, 255)
        backend.grab_frame()
    assert sck.SCShareableContent.getShareableContentWithCompletionHandler_.call_count == 1
    config = sck.SCStreamConfiguration.alloc.return_value.init.return_value
    config.setWidth_.assert_called_with(1600)
    config.setHeight_.assert_called_with(1200)


def test_grab_frame_window_closed_raises():
    with _macos_modules(_fake_quartz(WINDOWS), _fake_sck([10])):
        backend = macos.MacOSCapture()
        backend.select_window(WindowInfo(99, "Closed"))
        with pytest.raises(CaptureError, match="gone"):
            backend.grab_frame()


def test_grab_frame_window_not_shareable_raises():
    with _macos_modules(_fake_quartz(WINDOWS), _fake_sck([11])):
        backend = macos.MacOSCapture()
        backend.select_window(WindowInfo(10, "Ryujinx", "Zelda"))
        with pytest.raises(CaptureError, match="not capturable"):
            backend.grab_frame()


def test_grab_frame_permission_declined_by_screencapturekit():
    error = MagicMock(**{"code.return_value": -3801})
    with _macos_modules(_fake_quartz(WINDOWS), _fake_sck([10], image=None, error=error)):
        backend = macos.MacOSCapture()
        backend.select_window(WindowInfo(10, "Ryujinx", "Zelda"))
        with pytest.raises(CaptureError, match="Screen Recording permission"):
            backend.grab_frame()


def test_grab_frame_image_conversion_error_is_reported():
    quartz = _fake_quartz(WINDOWS)
    with _macos_modules(quartz, _fake_sck([10])):
        backend = macos.MacOSCapture()
        backend.select_window(WindowInfo(10, "Ryujinx", "Zelda"))
        quartz.CGDataProviderCopyData.return_value = None
        with pytest.raises(CaptureError, match="Could not read the captured image"):
            backend.grab_frame()


def test_raise_sck_error_other_error_uses_its_description():
    error = MagicMock(**{"code.return_value": -1, "localizedDescription.return_value": "boom"})
    with pytest.raises(CaptureError, match="boom"):
        macos.MacOSCapture._raise_sck_error(error)
    with pytest.raises(CaptureError, match="unknown error"):
        macos.MacOSCapture._raise_sck_error(None)


def test_wait_timeout_raises():
    import queue
    with patch.object(macos, "_TIMEOUT_S", 0.01):
        with pytest.raises(CaptureError, match="timeout"):
            macos.MacOSCapture._wait(queue.Queue())
