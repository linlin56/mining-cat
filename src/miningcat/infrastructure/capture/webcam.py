import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PIL import Image

from miningcat.infrastructure.capture.base import CaptureBackend, CaptureError, WindowInfo

MACOS_PERMISSION_HINT = (
    "MiningCat needs the Camera permission to read a webcam or capture card.\n"
    "Open System Settings > Privacy & Security > Camera, "
    "enable the app you launched MiningCat from (Terminal, iTerm2, VS Code...), then restart that app."
)

# AVAuthorizationStatus values.
_AV_NOT_DETERMINED, _AV_AUTHORIZED = 0, 3

# Frames grabbed, and time waited, before the first frame is handed out: webcams need a moment to settle their exposure,
# white balance and focus (about a second on macOS), and their first frames are dark or blurry until then.
_WARMUP_FRAMES = 5
_WARMUP_S = 1.5
_TIMEOUT_S = 5
# Consecutive failed grabs before the device is considered gone (unplugged, taken by another app...).
_MAX_FAILURES = 50

# Asked for on Linux and Windows, where drivers often default to 640x480 (too small for in-game text):
# the driver picks its closest supported size. MJPG keeps 1080p at full frame rate over USB 2.
_WANTED_SIZE = (1920, 1080)

_SYS_V4L = Path("/sys/class/video4linux")


def _video_index(name: str) -> int:
    return int(name.removeprefix("video"))


# Webcams and capture cards (HDMI capture boxes for a console or another computer), read with OpenCV.
# A device is a WindowInfo whose `id` is its OpenCV index and `owner` its name. Indices change when devices are
# plugged in or out, so the name is what's saved, and the index only breaks ties between devices with the same name.
class WebcamCapture(CaptureBackend):
    has_system_picker = False

    def __init__(self):
        try:
            import cv2
        except ImportError as exc:
            raise CaptureError(f"{exc}\nWebcam capture needs OpenCV: run `make install`.") from exc
        self._cv2 = cv2
        # Same OpenCV backend as the one the device names are listed with, so that indices match.
        self._api = {"darwin": cv2.CAP_AVFOUNDATION, "linux": cv2.CAP_V4L2, "win32": cv2.CAP_DSHOW}.get(sys.platform, cv2.CAP_ANY)
        self._device: WindowInfo | None = None
        self._reader: _FrameReader | None = None

    # CaptureBackend

    def list_windows(self) -> list[WindowInfo]:
        names = self._device_names()
        if not names:
            raise CaptureError("No webcam or capture card found: is it plugged in?")
        return [WindowInfo(id=index, owner=name) for index, name in names]

    def select_window(self, window: WindowInfo | None = None) -> None:
        if window is None:
            raise CaptureError("Pick a camera from list_windows() first.")
        self.close()
        self._device = window

    # Found back by name (its index may have changed), the saved index first if several devices share the name.
    def restore(self, state: dict) -> None:
        if not state.get("name"):
            raise CaptureError("No camera saved: select the camera again.")
        devices = self.list_windows()
        same_name = [d for d in devices if d.owner == state["name"]]
        match = next((d for d in same_name if d.id == state.get("index")), None) or next(iter(same_name), None)
        if match is None:
            raise CaptureError(f"Camera '{state['name']}' not found: is it plugged in? Otherwise select the camera again.")
        self.select_window(match)
        # A saved camera is restored to capture from it: turned on right away, so that it has settled by the first capture.
        self._start()

    @property
    def state(self) -> dict:
        if self._device is None:
            return {}
        return {"index": self._device.id, "name": self._device.owner}

    @property
    def window_label(self) -> str:
        return self._device.label if self._device else ""

    # The device is opened on the first call (or by restore()): selecting a camera doesn't turn it on.
    def grab_frame(self) -> Image.Image:
        if self._device is None:
            raise CaptureError("No camera selected.")
        frame = self._start().latest()
        return Image.fromarray(self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB))

    def close(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None

    # helpers

    def _start(self) -> "_FrameReader":
        if self._reader is None:
            self._reader = _FrameReader(self._cv2, self._api, self._device)
        return self._reader

    # [(OpenCV index, name)] of the video devices, in OpenCV's order for self._api.
    def _device_names(self) -> list[tuple[int, str]]:
        if sys.platform == "darwin":
            return _macos_devices()
        if sys.platform == "linux":
            return _linux_devices()
        if sys.platform == "win32":
            names = _directshow_devices()
            if names:
                return names
        return self._probe_devices()

    # Last resort without device names: opens indices until one fails.
    def _probe_devices(self, limit: int = 10) -> list[tuple[int, str]]:
        devices = []
        for index in range(limit):
            capture = self._cv2.VideoCapture(index, self._api)
            try:
                if not capture.isOpened():
                    break
                devices.append((index, f"Camera {index + 1}"))
            finally:
                capture.release()
        return devices


# Opens the device and grabs every frame it sends, in its own thread: reading only when asked would return frames that
# waited in the driver's buffer, from before the text changed. Frames are only decoded when latest() asks for one.
# The OpenCV capture is opened, read and released by that thread alone.
class _FrameReader:
    def __init__(self, cv2, api: int, device: WindowInfo):
        self._cv2, self._api, self._device = cv2, api, device
        self._requests: queue.Queue[queue.Queue] = queue.Queue()
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._error: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # BGR array of the last frame the device sent.
    def latest(self):
        if not self._ready.wait(_WARMUP_S + _TIMEOUT_S):
            raise CaptureError(f"'{self._device.label}' didn't send any image in time: is it used by another app (OBS...)?")
        if self._error:
            raise CaptureError(self._error)
        reply: queue.Queue = queue.Queue()
        self._requests.put(reply)
        try:
            frame = reply.get(timeout=_TIMEOUT_S)
        except queue.Empty:
            frame = None
        if frame is None:
            raise CaptureError(self._error or f"Could not read an image from '{self._device.label}'.")
        return frame

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        capture = self._open()
        if capture is None:
            self._fail(f"Could not open '{self._device.label}': is it plugged in, and not used by another app (OBS...)?")
            return
        try:
            self._pump(capture)
        finally:
            capture.release()
            self._fail(self._error or "The camera was closed.")

    def _open(self):
        cv2 = self._cv2
        capture = cv2.VideoCapture(self._device.id, self._api)
        if not capture.isOpened():
            capture.release()
            return None
        if sys.platform != "darwin":
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, _WANTED_SIZE[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, _WANTED_SIZE[1])
        return capture

    def _pump(self, capture) -> None:
        grabbed = failures = 0
        warm_at = time.monotonic() + _WARMUP_S
        while not self._stopping.is_set():
            if not capture.grab():
                failures += 1
                if failures >= _MAX_FAILURES:
                    self._error = f"'{self._device.label}' stopped sending images: was it unplugged?"
                    return
                time.sleep(0.02)
                continue
            grabbed, failures = grabbed + 1, 0
            if grabbed >= _WARMUP_FRAMES and time.monotonic() >= warm_at:
                self._ready.set()
            while not self._requests.empty():
                ok, frame = capture.retrieve()
                self._requests.get_nowait().put(frame if ok else None)

    # Ends the pending and future latest() calls with `message`.
    def _fail(self, message: str) -> None:
        self._error = message
        self._ready.set()
        while not self._requests.empty():
            self._requests.get_nowait().put(None)


# Same discovery session as OpenCV's AVFoundation backend, hence the same order. Also checks the Camera permission,
# without which OpenCV only fails silently.
def _macos_devices() -> list[tuple[int, str]]:
    try:
        import AVFoundation as AV
    except ImportError as exc:
        raise CaptureError(f"{exc}\nmacOS webcam capture needs pyobjc: run `make install`.") from exc
    status = AV.AVCaptureDevice.authorizationStatusForMediaType_(AV.AVMediaTypeVideo)
    if status == _AV_NOT_DETERMINED:
        AV.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AV.AVMediaTypeVideo, lambda _granted: None)
        raise CaptureError("Allow the camera access asked by macOS, then try again.")
    if status != _AV_AUTHORIZED:
        raise CaptureError(MACOS_PERMISSION_HINT)
    external = getattr(AV, "AVCaptureDeviceTypeExternal", None) or AV.AVCaptureDeviceTypeExternalUnknown
    session = AV.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_(
        [AV.AVCaptureDeviceTypeBuiltInWideAngleCamera, external], AV.AVMediaTypeVideo, AV.AVCaptureDevicePositionUnspecified,
    )
    return [(index, str(device.localizedName())) for index, device in enumerate(session.devices())]


# /dev/videoN is OpenCV index N. A device often has a second node for its metadata (index 1), which can't be read.
def _linux_devices(root: Path = _SYS_V4L) -> list[tuple[int, str]]:
    if not root.is_dir():
        return []
    devices = []
    for node in sorted(root.glob("video*"), key=lambda p: _video_index(p.name)):
        try:
            if (node / "index").exists() and (node / "index").read_text().strip() != "0":
                continue
            devices.append((_video_index(node.name), (node / "name").read_text().strip() or node.name))
        except (OSError, ValueError):
            continue
    return devices


_DSHOW_VIDEO = re.compile(r'"(?P<name>[^"]+)"\s+\(video\)')


# DirectShow lists its devices in the same order as OpenCV's CAP_DSHOW, and ffmpeg prints their names.
def _directshow_devices() -> list[tuple[int, str]]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return []
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_directshow_devices(result.stderr)


def parse_directshow_devices(output: str) -> list[tuple[int, str]]:
    names = [m["name"] for m in _DSHOW_VIDEO.finditer(output)]
    return list(enumerate(names))
