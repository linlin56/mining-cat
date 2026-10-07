import contextlib
import ctypes
import os
from unittest.mock import MagicMock, patch

import pytest

from game_ocr.capture import CaptureError, WindowInfo
from game_ocr.capture import windows

W, H = 4, 2
# BGRA pixels: pure blue (B=255) once converted to RGB
_BGRA_BLUE = bytes([255, 0, 0, 255]) * (W * H)

_WS_EX_TOOLWINDOW = windows._WS_EX_TOOLWINDOW
_OWN_PID = os.getpid()

# hwnd -> window data. Order matters: it's the GetTopWindow / GetWindow(NEXT) z-order the fake API walks.
WINDOWS = {
    10: dict(title="Sample Quest", class_name="SampleAppWnd", pid=100, proc_name="SampleApp.exe", rect=(0, 0, 800, 600)),
    11: dict(title="Main Menu", class_name="MenuWndClass", pid=101, proc_name=None, rect=(0, 0, 800, 600)),
    12: dict(title="Tooltip", class_name="Tip", pid=102, proc_name="explorer.exe", rect=(0, 0, 800, 600), ex_style=_WS_EX_TOOLWINDOW),
    13: dict(title="Tiny", class_name="Tiny", pid=103, proc_name="tiny.exe", rect=(0, 0, 20, 20)),
    14: dict(title="Console", class_name="Console", pid=_OWN_PID, proc_name="python.exe", rect=(0, 0, 800, 600)),
    15: dict(title="Cloaked", class_name="Cloaked", pid=105, proc_name="cloaked.exe", rect=(0, 0, 800, 600), cloaked=1),
    16: dict(title="Minimized Game", class_name="Game", pid=106, proc_name="mini.exe", rect=(0, 0, 800, 600), iconic=True),
    17: dict(title="", class_name="NoTitle", pid=107, proc_name="notitle.exe", rect=(0, 0, 800, 600)),
}
ORDER = list(WINDOWS)


def _fake_user32():
    user32 = MagicMock()
    user32.GetTopWindow.side_effect = lambda _hwnd: ORDER[0]
    user32.GetWindow.side_effect = lambda hwnd, _flag: ORDER[ORDER.index(hwnd) + 1] if ORDER.index(hwnd) + 1 < len(ORDER) else 0
    user32.IsWindowVisible.return_value = True
    user32.IsWindow.return_value = True
    user32.IsIconic.side_effect = lambda hwnd: bool(WINDOWS[hwnd].get("iconic"))
    user32.GetWindowTextLengthW.side_effect = lambda hwnd: len(WINDOWS[hwnd]["title"])

    def get_window_text(hwnd, buf, _n):
        buf.value = WINDOWS[hwnd]["title"]
        return len(buf.value)
    user32.GetWindowTextW.side_effect = get_window_text

    def get_class_name(hwnd, buf, _n):
        buf.value = WINDOWS[hwnd]["class_name"]
        return len(buf.value)
    user32.GetClassNameW.side_effect = get_class_name

    user32.GetWindowLongW.side_effect = lambda hwnd, _index: WINDOWS[hwnd].get("ex_style", 0)

    def get_thread_pid(hwnd, pid_ptr):
        pid_ptr.contents.value = WINDOWS[hwnd]["pid"]
        return 1
    user32.GetWindowThreadProcessId.side_effect = get_thread_pid

    def get_window_rect(hwnd, rect_ptr):
        left, top, right, bottom = WINDOWS[hwnd]["rect"]
        rect_ptr.contents.left, rect_ptr.contents.top = left, top
        rect_ptr.contents.right, rect_ptr.contents.bottom = right, bottom
        return True
    user32.GetWindowRect.side_effect = get_window_rect
    return user32


def _fake_kernel32():
    kernel32 = MagicMock()

    def open_process(_flags, _inherit, pid):
        entry = next((w for w in WINDOWS.values() if w["pid"] == pid), None)
        return pid if entry and entry["proc_name"] else 0
    kernel32.OpenProcess.side_effect = open_process

    def query_image_name(handle, _flags, buf, _size_ptr):
        entry = next(w for w in WINDOWS.values() if w["pid"] == handle)
        buf.value = f"C:\\Games\\{entry['proc_name']}"
        return True
    kernel32.QueryFullProcessImageNameW.side_effect = query_image_name
    kernel32.CloseHandle.return_value = True
    return kernel32


def _fake_dwmapi():
    dwmapi = MagicMock()

    def get_attribute(hwnd, _attr, value_ptr, _size):
        value_ptr.contents.value = WINDOWS[hwnd].get("cloaked", 0)
        return 0
    dwmapi.DwmGetWindowAttribute.side_effect = get_attribute
    return dwmapi


@contextlib.contextmanager
def _windows_modules(user32=None, gdi32=None, kernel32=None, dwmapi=None):
    dlls = {
        "user32": user32 or _fake_user32(), "gdi32": gdi32 or MagicMock(),
        "kernel32": kernel32 or _fake_kernel32(), "dwmapi": dwmapi or _fake_dwmapi(),
    }
    with patch.object(windows.ctypes, "WinDLL", lambda name, **_kwargs: dlls[name], create=True):
        yield dlls


# init
def test_init_without_windows_api_raises():
    with patch.object(windows.ctypes, "WinDLL", MagicMock(side_effect=OSError("boom")), create=True):
        with pytest.raises(CaptureError, match="Windows API"):
            windows.WindowsCapture()


# list_windows
def test_list_windows_filters_out_everything_but_real_app_windows():
    with _windows_modules():
        result = windows.WindowsCapture().list_windows()
    assert result == [WindowInfo(10, "SampleApp", "Sample Quest"), WindowInfo(11, "MenuWndClass", "Main Menu")]


def test_list_windows_falls_back_to_class_name_without_a_process_name():
    with _windows_modules() as dlls:
        windows.WindowsCapture().list_windows()
    # pid 100 (hwnd 10) resolves and is closed; pid 101 (hwnd 11) never got a handle, so there's nothing to close for it.
    dlls["kernel32"].CloseHandle.assert_called_once()


# select / restore / state
def test_select_window_requires_a_window():
    with _windows_modules():
        with pytest.raises(CaptureError):
            windows.WindowsCapture().select_window(None)


def test_state_and_label_follow_selected_window():
    with _windows_modules():
        backend = windows.WindowsCapture()
        assert backend.state == {} and backend.window_label == ""
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        assert backend.state == {"id": 10, "owner": "SampleApp", "title": "Sample Quest"}
        assert backend.window_label == "SampleApp - Sample Quest"


@pytest.mark.parametrize("state, expected_id", [
    ({"id": 10, "owner": "SampleApp", "title": "Sample Quest"}, 10),                  # same window id
    ({"id": 999, "owner": "SampleApp", "title": "Sample Quest"}, 10),                 # app restarted: same owner + title
    ({"id": 999, "owner": "MenuWndClass", "title": "Old title"}, 11),       # title changed: same owner
])
def test_restore_finds_the_saved_window(state, expected_id):
    with _windows_modules():
        backend = windows.WindowsCapture()
        backend.restore(state)
    assert backend.state["id"] == expected_id


def test_restore_window_not_found_raises():
    with _windows_modules():
        with pytest.raises(CaptureError, match="not found"):
            windows.WindowsCapture().restore({"id": 1, "owner": "Closed game"})


def test_restore_without_saved_window_raises():
    with _windows_modules():
        with pytest.raises(CaptureError, match="No window saved"):
            windows.WindowsCapture().restore({})


# grab_frame
def test_grab_frame_without_window_raises():
    with _windows_modules():
        with pytest.raises(CaptureError, match="No window selected"):
            windows.WindowsCapture().grab_frame()


def test_grab_frame_window_closed_raises():
    user32 = _fake_user32()
    user32.IsWindow.return_value = False
    with _windows_modules(user32=user32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="gone"):
            backend.grab_frame()


def test_grab_frame_rect_unavailable_raises():
    user32 = _fake_user32()
    user32.GetWindowRect.side_effect = None
    user32.GetWindowRect.return_value = False  # window closed between IsWindow() and the rect lookup
    with _windows_modules(user32=user32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="gone"):
            backend.grab_frame()


def test_grab_frame_empty_rect_raises():
    user32 = _fake_user32()

    def get_window_rect(_hwnd, rect_ptr):
        rect_ptr.contents.left, rect_ptr.contents.top = 0, 0
        rect_ptr.contents.right, rect_ptr.contents.bottom = 0, 0
        return True
    user32.GetWindowRect.side_effect = get_window_rect
    with _windows_modules(user32=user32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="no visible content"):
            backend.grab_frame()


def test_process_name_returns_none_when_the_query_fails():
    kernel32 = _fake_kernel32()
    kernel32.QueryFullProcessImageNameW.side_effect = None
    kernel32.QueryFullProcessImageNameW.return_value = False
    with _windows_modules(kernel32=kernel32):
        backend = windows.WindowsCapture()
        assert backend._process_name(WINDOWS[10]["pid"]) is None
    kernel32.CloseHandle.assert_called_once()


def test_grab_frame_minimized_raises():
    with _windows_modules():
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(16, "Game", "Minimized Game"))
        with pytest.raises(CaptureError, match="minimized"):
            backend.grab_frame()


def test_grab_frame_print_window_failure_raises():
    user32 = _fake_user32()
    user32.GetWindowDC.return_value = 1234
    user32.PrintWindow.return_value = False
    with _windows_modules(user32=user32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="Could not capture"):
            backend.grab_frame()


def test_grab_frame_no_device_context_raises():
    user32 = _fake_user32()
    user32.GetWindowDC.return_value = 0
    with _windows_modules(user32=user32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="device context"):
            backend.grab_frame()


def test_grab_frame_reads_the_captured_bitmap():
    user32 = _fake_user32()
    user32.GetWindowDC.return_value = 1234
    user32.PrintWindow.return_value = True

    def get_window_rect(_hwnd, rect_ptr):
        rect_ptr.contents.left, rect_ptr.contents.top = 0, 0
        rect_ptr.contents.right, rect_ptr.contents.bottom = W, H
        return True
    user32.GetWindowRect.side_effect = get_window_rect

    gdi32 = MagicMock()

    def get_dibits(_mem_dc, _bitmap, _start, _lines, buffer, _info_ptr, _usage):
        ctypes.memmove(buffer, _BGRA_BLUE, len(_BGRA_BLUE))
        return H
    gdi32.GetDIBits.side_effect = get_dibits

    with _windows_modules(user32=user32, gdi32=gdi32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        image = backend.grab_frame()
    assert image.size == (W, H)
    assert image.getpixel((0, 0)) == (0, 0, 255)
    gdi32.DeleteObject.assert_called_once()
    gdi32.DeleteDC.assert_called_once()
    user32.ReleaseDC.assert_called_once()


def test_grab_frame_dibits_failure_raises():
    user32 = _fake_user32()
    user32.GetWindowDC.return_value = 1234
    user32.PrintWindow.return_value = True
    gdi32 = MagicMock()
    gdi32.GetDIBits.return_value = 0
    with _windows_modules(user32=user32, gdi32=gdi32):
        backend = windows.WindowsCapture()
        backend.select_window(WindowInfo(10, "SampleApp", "Sample Quest"))
        with pytest.raises(CaptureError, match="Could not read the captured image"):
            backend.grab_frame()
