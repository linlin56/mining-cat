import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from miningcat.infrastructure.capture import CaptureError, WindowInfo, webcam

# BGR pixels: pure blue (B=255) once converted to RGB
_BGR_BLUE = np.zeros((2, 4, 3), dtype=np.uint8)
_BGR_BLUE[:, :, 0] = 255


class FakeVideoCapture:
    def __init__(self, cv2, index, api):
        self.cv2, self.index, self.api = cv2, index, api
        self.props = {}
        self.released = False
        cv2.opened.append(self)

    def isOpened(self):
        return self.index in self.cv2.devices

    def set(self, prop, value):
        self.props[prop] = value

    def grab(self):
        time.sleep(0.001)
        return self.cv2.grab_ok

    def retrieve(self):
        return True, _BGR_BLUE.copy()

    def release(self):
        self.released = True


def _fake_cv2(devices=(0,), grab_ok=True):
    cv2 = SimpleNamespace(
        CAP_ANY=0, CAP_AVFOUNDATION=1200, CAP_V4L2=200, CAP_DSHOW=700,
        CAP_PROP_FOURCC=6, CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, COLOR_BGR2RGB=4,
        devices=set(devices), grab_ok=grab_ok, opened=[],
    )
    cv2.VideoCapture = lambda index, api: FakeVideoCapture(cv2, index, api)
    cv2.VideoWriter_fourcc = lambda *chars: "".join(chars)
    cv2.cvtColor = lambda frame, _code: frame[:, :, ::-1]
    return cv2


def _backend(cv2, platform="linux", devices=((0, "Capture box"), (2, "Webcam"))):
    with patch.dict("sys.modules", {"cv2": cv2}), patch.object(webcam.sys, "platform", platform):
        backend = webcam.WebcamCapture()
    backend._device_names = lambda: list(devices)
    return backend


@pytest.fixture(autouse=True)
def no_warmup_delay(monkeypatch):
    monkeypatch.setattr(webcam, "_WARMUP_S", 0)


@pytest.fixture
def linux():
    with patch.object(webcam.sys, "platform", "linux"):
        yield


def test_missing_opencv_explains_how_to_install():
    with patch.dict("sys.modules", {"cv2": None}):
        with pytest.raises(CaptureError, match="needs OpenCV"):
            webcam.WebcamCapture()


@pytest.mark.parametrize("platform, api", [("darwin", 1200), ("linux", 200), ("win32", 700), ("freebsd", 0)])
def test_opencv_backend_matches_the_device_listing(platform, api):
    assert _backend(_fake_cv2(), platform)._api == api


def test_list_windows_lists_devices_by_name():
    backend = _backend(_fake_cv2())
    assert backend.list_windows() == [WindowInfo(0, "Capture box"), WindowInfo(2, "Webcam")]
    assert backend.list_windows()[0].label == "Capture box"


def test_list_windows_without_device_raises():
    with pytest.raises(CaptureError, match="No webcam or capture card found"):
        _backend(_fake_cv2(), devices=()).list_windows()


def test_select_then_state_and_label():
    backend = _backend(_fake_cv2())
    backend.select_window(WindowInfo(2, "Webcam"))
    assert backend.state == {"index": 2, "name": "Webcam"}
    assert backend.window_label == "Webcam"


def test_nothing_selected():
    backend = _backend(_fake_cv2())
    assert backend.state == {}
    assert backend.window_label == ""
    with pytest.raises(CaptureError, match="Pick a camera"):
        backend.select_window(None)
    with pytest.raises(CaptureError, match="No camera selected"):
        backend.grab_frame()


def test_restore_finds_the_device_by_name_when_its_index_changed():
    backend = _backend(_fake_cv2(), devices=((0, "Webcam"), (1, "Capture box")))
    backend.restore({"index": 0, "name": "Capture box"})
    assert backend.state == {"index": 1, "name": "Capture box"}
    backend.close()


def test_restore_turns_the_camera_on_so_it_settles_before_the_first_capture(linux):
    cv2 = _fake_cv2(devices=(1,))
    backend = _backend(cv2, devices=((1, "Capture box"),))
    backend.restore({"index": 1, "name": "Capture box"})
    backend.grab_frame()
    assert len(cv2.opened) == 1  # opened by restore(), reused by grab_frame()
    backend.close()


def test_restore_prefers_the_saved_index_among_devices_of_the_same_name():
    backend = _backend(_fake_cv2(), devices=((0, "USB Video"), (1, "USB Video")))
    backend.restore({"index": 1, "name": "USB Video"})
    assert backend.state == {"index": 1, "name": "USB Video"}
    backend.close()


@pytest.mark.parametrize("state, message", [({}, "No camera saved"), ({"index": 0, "name": "Gone"}, "'Gone' not found")])
def test_restore_failures(state, message):
    with pytest.raises(CaptureError, match=message):
        _backend(_fake_cv2()).restore(state)


def test_grab_frame_opens_the_device_lazily_and_returns_rgb(linux):
    cv2 = _fake_cv2()
    backend = _backend(cv2)
    backend.select_window(WindowInfo(0, "Capture box"))
    assert cv2.opened == []  # selecting doesn't turn the camera on
    image = backend.grab_frame()
    assert image.size == (4, 2)
    assert image.getpixel((0, 0)) == (0, 0, 255)
    backend.grab_frame()
    assert len(cv2.opened) == 1  # opened once
    capture = cv2.opened[0]
    assert (capture.index, capture.api) == (0, 200)
    backend.close()
    assert capture.released


def test_linux_and_windows_ask_for_full_hd_mjpg(linux):
    cv2 = _fake_cv2()
    with _backend(cv2) as backend:
        backend.select_window(WindowInfo(0, "Capture box"))
        backend.grab_frame()
    assert cv2.opened[0].props == {6: "MJPG", 3: 1920, 4: 1080}


def test_macos_keeps_the_device_format():
    cv2 = _fake_cv2()
    with patch.object(webcam.sys, "platform", "darwin"), _backend(cv2, "darwin") as backend:
        backend.select_window(WindowInfo(0, "Capture box"))
        backend.grab_frame()
    assert cv2.opened[0].props == {}


def test_device_that_cannot_be_opened(linux):
    backend = _backend(_fake_cv2(devices=()))
    backend.select_window(WindowInfo(0, "Capture box"))
    with pytest.raises(CaptureError, match="Could not open 'Capture box'"):
        backend.grab_frame()
    backend.close()


def test_device_that_stops_sending_images(linux, monkeypatch):
    monkeypatch.setattr(webcam, "_MAX_FAILURES", 2)
    backend = _backend(_fake_cv2(grab_ok=False))
    backend.select_window(WindowInfo(0, "Capture box"))
    with pytest.raises(CaptureError, match="stopped sending images"):
        backend.grab_frame()
    backend.close()


def test_selecting_another_device_closes_the_previous_one(linux):
    cv2 = _fake_cv2(devices=(0, 2))
    backend = _backend(cv2)
    backend.select_window(WindowInfo(0, "Capture box"))
    backend.grab_frame()
    backend.select_window(WindowInfo(2, "Webcam"))
    assert cv2.opened[0].released
    backend.grab_frame()
    assert cv2.opened[1].index == 2
    backend.close()


# device names per OS
def test_linux_devices_skip_metadata_nodes(tmp_path):
    for node, name, index in [("video0", "Capture box", "0"), ("video1", "Capture box", "1"), ("video10", "Webcam", "0")]:
        (tmp_path / node).mkdir()
        (tmp_path / node / "name").write_text(name + "\n")
        (tmp_path / node / "index").write_text(index + "\n")
    (tmp_path / "video2").mkdir()
    (tmp_path / "video2" / "name").write_text("Old driver\n")  # no index file: kept
    assert webcam._linux_devices(tmp_path) == [(0, "Capture box"), (2, "Old driver"), (10, "Webcam")]


def test_linux_without_video4linux(tmp_path):
    assert webcam._linux_devices(tmp_path / "missing") == []


def test_parse_directshow_devices():
    output = (
        '[dshow @ 0001] "USB Video" (video)\n'
        '[dshow @ 0001]   Alternative name "@device_pnp_\\\\?\\usb#vid"\n'
        '[dshow @ 0001] "Microphone (USB Video)" (audio)\n'
        '[dshow @ 0001] "OBS Virtual Camera" (video)\n'
        "dummy: Immediate exit requested\n"
    )
    assert webcam.parse_directshow_devices(output) == [(0, "USB Video"), (1, "OBS Virtual Camera")]


def test_windows_without_ffmpeg_probes_indices():
    cv2 = _fake_cv2(devices=(0, 1))
    with patch.dict("sys.modules", {"cv2": cv2}), patch.object(webcam.sys, "platform", "win32"), \
         patch.object(webcam.shutil, "which", return_value=None):
        backend = webcam.WebcamCapture()
        assert backend.list_windows() == [WindowInfo(0, "Camera 1"), WindowInfo(1, "Camera 2")]
    assert all(c.released for c in cv2.opened)


def _fake_avfoundation(status, names=("Capture box", "FaceTime HD")):
    av = MagicMock()
    av.AVCaptureDevice.authorizationStatusForMediaType_.return_value = status
    devices = [MagicMock(**{"localizedName.return_value": n}) for n in names]
    av.AVCaptureDeviceDiscoverySession.discoverySessionWithDeviceTypes_mediaType_position_.return_value.devices.return_value = devices
    return av


def test_macos_devices():
    with patch.dict("sys.modules", {"AVFoundation": _fake_avfoundation(3)}):
        assert webcam._macos_devices() == [(0, "Capture box"), (1, "FaceTime HD")]


def test_macos_asks_for_the_camera_permission_the_first_time():
    av = _fake_avfoundation(0)
    with patch.dict("sys.modules", {"AVFoundation": av}):
        with pytest.raises(CaptureError, match="Allow the camera access"):
            webcam._macos_devices()
    av.AVCaptureDevice.requestAccessForMediaType_completionHandler_.assert_called_once()


def test_macos_camera_permission_denied():
    with patch.dict("sys.modules", {"AVFoundation": _fake_avfoundation(2)}):
        with pytest.raises(CaptureError, match="Privacy & Security > Camera"):
            webcam._macos_devices()
