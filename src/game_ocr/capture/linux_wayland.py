import secrets
import threading

from PIL import Image

from game_ocr.capture.base import CaptureBackend, CaptureError

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJ_PATH = "/org/freedesktop/portal/desktop"
IFACE_SCREENCAST = "org.freedesktop.portal.ScreenCast"
IFACE_REQUEST = "org.freedesktop.portal.Request"

_SIGNATURES = {
    "CreateSession": "(a{sv})",
    "SelectSources": "(oa{sv})",
    "Start": "(osa{sv})",
}

_SOURCE_TYPE_WINDOW = 2   # a single window (not the whole screen)
_CURSOR_HIDDEN = 1
_PERSIST_UNTIL_REVOKED = 2

_INSTALL_HINT = (
    "Linux capture needs PyGObject and GStreamer's PipeWire plugin:\n"
    "  sudo apt install python3-gi gir1.2-gst-plugins-base-1.0 gstreamer1.0-pipewire\n"
    "and a virtual environment that can see them (python3 -m venv --system-site-packages .venv)."
)


def _import_gi():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        gi.require_version("GstVideo", "1.0")
        from gi.repository import Gio, GLib, Gst, GstVideo
    except (ImportError, ValueError) as exc:
        raise CaptureError(f"{exc}\n{_INSTALL_HINT}") from exc
    Gst.init(None)
    return Gio, GLib, Gst, GstVideo


def _token() -> str:
    return "u" + secrets.token_hex(8)


# One portal ScreenCast session plus the GStreamer pipeline reading it.
# Keep the instance alive while capturing: the portal session and PipeWire pipeline are opened once,
# then grab_frame() can be called repeatedly without going through D-Bus or triggering a popup again.
class WaylandPortalCapture(CaptureBackend):
    has_system_picker = True

    def __init__(self):
        self._Gio, self._GLib, self._Gst, self._GstVideo = _import_gi()
        self._bus = self._Gio.bus_get_sync(self._Gio.BusType.SESSION, None)
        self._sender = self._bus.get_unique_name()[1:].replace(".", "_")
        self._loop = self._GLib.MainLoop()
        threading.Thread(target=self._loop.run, daemon=True).start()
        self._session_handle = None
        self._node_id = None
        self._pw_fd = None
        self._restore_token: str | None = None
        self._pipeline = None
        self._appsink = None

    # ---- CaptureBackend ----

    def list_windows(self):
        raise CaptureError("The desktop portal picks the window itself: call select_window() instead.")

    # Always asks the user to pick a window in GNOME's portal dialog.
    def select_window(self, window=None) -> None:
        self._open(restore_token=None)
        self._start_pipeline()

    def restore(self, state: dict) -> None:
        token = state.get("restore_token")
        if not token:
            raise CaptureError("No saved screen capture permission: select the window again.")
        try:
            self._open(restore_token=token)
        except CaptureError as exc:
            raise CaptureError(f"{exc}\nThe permission may have been revoked: select the window again.") from exc
        self._start_pipeline()

    # Restore tokens are single-use: the portal returns a new one on each Start, so the state must be saved again after every restore().
    @property
    def state(self) -> dict:
        return {"restore_token": self._restore_token}

    @property
    def window_label(self) -> str:
        return "Window shared through the desktop portal"

    def grab_frame(self, timeout_s: float = 5) -> Image.Image:
        Gst, GstVideo = self._Gst, self._GstVideo
        if self._appsink is None:
            raise CaptureError("No window selected.")
        sample = self._appsink.emit("try-pull-sample", int(Gst.SECOND * timeout_s))
        if sample is None:
            raise CaptureError("No frame received from PipeWire (timeout) - did the stream stop?")
        buf = sample.get_buffer()
        info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            raise CaptureError("Could not map the video buffer")
        try:
            img = Image.frombytes("RGB", (info.width, info.height), bytes(mapinfo.data), "raw", "RGB", info.stride[0])
        finally:
            buf.unmap(mapinfo)
        return img.copy()

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(self._Gst.State.NULL)
            self._pipeline = None
            self._appsink = None
        if self._session_handle is not None:
            try:
                self._bus.call_sync(
                    BUS_NAME, self._session_handle, "org.freedesktop.portal.Session",
                    "Close", None, None, self._Gio.DBusCallFlags.NONE, -1, None)
            except self._GLib.Error:
                pass
            self._session_handle = None
        self._loop.quit()

    # ---- portal calls ----

    # Calls a portal method that returns a request handle, waits for the matching Response signal and returns its results.
    def _request(self, method: str, args: tuple, timeout: float = 120) -> dict:
        Gio, GLib = self._Gio, self._GLib
        handle_token = _token()
        opts = dict(args[-1])
        opts["handle_token"] = GLib.Variant("s", handle_token)
        args = args[:-1] + (opts,)
        request_path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{handle_token}"

        result = {}
        event = threading.Event()

        def on_response(_connection, _sender_name, _path, _iface, _signal, params):
            result["code"], result["results"] = params.unpack()
            event.set()

        sub_id = self._bus.signal_subscribe(
            BUS_NAME, IFACE_REQUEST, "Response", request_path,
            None, Gio.DBusSignalFlags.NONE, on_response)
        try:
            self._bus.call_sync(
                BUS_NAME, OBJ_PATH, IFACE_SCREENCAST, method,
                GLib.Variant(_SIGNATURES[method], args),
                None, Gio.DBusCallFlags.NONE, -1, None)
            if not event.wait(timeout):
                raise CaptureError(f"{method}: the desktop portal didn't answer (timeout)")
        finally:
            self._bus.signal_unsubscribe(sub_id)

        if result["code"] != 0:
            raise CaptureError(f"{method}: refused or cancelled in the portal dialog (code {result['code']})")
        return result["results"]

    # Opens a ScreenCast session. With a valid restore_token no dialog is shown,
    # otherwise GNOME asks the user to pick a window, and a new persistent token is stored in self._restore_token.
    def _open(self, restore_token: str | None) -> None:
        Gio, GLib = self._Gio, self._GLib
        res = self._request("CreateSession", ({"session_handle_token": GLib.Variant("s", _token())},))
        self._session_handle = res["session_handle"]

        select_opts = {
            "types": GLib.Variant("u", _SOURCE_TYPE_WINDOW),
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", _CURSOR_HIDDEN),
            "persist_mode": GLib.Variant("u", _PERSIST_UNTIL_REVOKED),
        }
        if restore_token:
            select_opts["restore_token"] = GLib.Variant("s", restore_token)
        self._request("SelectSources", (self._session_handle, select_opts))

        start_res = self._request("Start", (self._session_handle, "", {}))
        streams = start_res.get("streams")
        if not streams:
            raise CaptureError("No window shared (cancelled?)")
        self._node_id, _stream_props = streams[0]
        self._restore_token = start_res.get("restore_token") or restore_token

        body, fd_list = self._bus.call_with_unix_fd_list_sync(
            BUS_NAME, OBJ_PATH, IFACE_SCREENCAST, "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (self._session_handle, {})),
            None, Gio.DBusCallFlags.NONE, -1, None, None)
        self._pw_fd = fd_list.get(body.unpack()[0])

    def _start_pipeline(self) -> None:
        Gst = self._Gst
        self._pipeline = Gst.parse_launch(
            f"pipewiresrc fd={self._pw_fd} path={self._node_id} do-timestamp=true "
            "! videoconvert ! video/x-raw,format=RGB "
            "! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true"
        )
        self._appsink = self._pipeline.get_by_name("sink")
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise CaptureError("The GStreamer/PipeWire pipeline failed to start")
