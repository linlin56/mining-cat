import ctypes
import ntpath
import os
from ctypes import wintypes

from PIL import Image

from game_ocr.capture.base import CaptureBackend, CaptureError, WindowInfo

# Ignore tiny helper windows (tray icons, tooltips...) that can't be a game window.
_MIN_WINDOW_SIZE = 50

_GW_HWNDNEXT = 2
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14  # sits on another virtual desktop, or is a suspended UWP app: not really "on screen"
_PW_RENDERFULLCONTENT = 0x00000002  # renders GPU-accelerated content too (DirectX, browsers...), needs Windows 8.1+
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_BI_RGB = 0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# Declares argtypes/restypes for the handle-returning functions: ctypes defaults to a 32-bit int otherwise,
# which truncates pointers on 64-bit Windows.
def _configure_winapi(user32, gdi32, kernel32, dwmapi) -> None:
    user32.GetTopWindow.restype = wintypes.HWND
    user32.GetTopWindow.argtypes = [wintypes.HWND]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
    ]

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


class WindowsCapture(CaptureBackend):
    has_system_picker = False

    def __init__(self):
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise CaptureError(f"{exc}\nWindows capture needs the Windows API.") from exc
        _configure_winapi(user32, gdi32, kernel32, dwmapi)
        self._user32, self._gdi32, self._kernel32, self._dwmapi = user32, gdi32, kernel32, dwmapi
        self._window: WindowInfo | None = None
        self._hwnd: int | None = None

    # ---- CaptureBackend ----

    def list_windows(self) -> list[WindowInfo]:
        user32 = self._user32
        own_pid = os.getpid()
        windows: list[WindowInfo] = []
        hwnd = user32.GetTopWindow(None)
        while hwnd:
            if self._is_capturable(hwnd, own_pid):
                windows.append(self._window_info(hwnd))
            hwnd = user32.GetWindow(hwnd, _GW_HWNDNEXT)
        return windows

    def select_window(self, window: WindowInfo | None = None) -> None:
        if window is None:
            raise CaptureError("Pick a window from list_windows() first.")
        self._window, self._hwnd = window, window.id

    # Window handles only live as long as the window: if the game was restarted, fall back to its process name + title, then process name alone.
    def restore(self, state: dict) -> None:
        if not state.get("owner"):
            raise CaptureError("No window saved: select the window again.")
        saved = WindowInfo(id=int(state.get("id", 0)), owner=state["owner"], title=state.get("title", ""))
        windows = self.list_windows()
        match = (
            next((w for w in windows if w.id == saved.id), None)
            or next((w for w in windows if (w.owner, w.title) == (saved.owner, saved.title)), None)
            or next((w for w in windows if w.owner == saved.owner), None)
        )
        if match is None:
            raise CaptureError(f"Window '{saved.label}' not found: is it open (and not minimized)? Otherwise select the window again.")
        self.select_window(match)

    @property
    def state(self) -> dict:
        if self._window is None:
            return {}
        return {"id": self._window.id, "owner": self._window.owner, "title": self._window.title}

    @property
    def window_label(self) -> str:
        return self._window.label if self._window else ""

    def grab_frame(self) -> Image.Image:
        if self._hwnd is None:
            raise CaptureError("No window selected.")
        if not self._user32.IsWindow(self._hwnd):
            raise CaptureError(f"Window '{self.window_label}' is gone: was it closed?")
        if self._user32.IsIconic(self._hwnd):
            raise CaptureError(f"Window '{self.window_label}' is minimized: restore it to capture.")
        return self._print_window()

    # ---- helpers ----

    def _is_capturable(self, hwnd: int, own_pid: int) -> bool:
        user32 = self._user32
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return False
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return False
        if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.pointer(pid))
        if pid.value == own_pid:
            return False
        cloaked = wintypes.DWORD()
        self._dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.pointer(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return False
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.pointer(rect))
        return rect.right - rect.left >= _MIN_WINDOW_SIZE and rect.bottom - rect.top >= _MIN_WINDOW_SIZE

    def _window_info(self, hwnd: int) -> WindowInfo:
        user32 = self._user32
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.pointer(pid))
        owner = self._process_name(pid.value) or self._class_name(hwnd) or title_buf.value
        return WindowInfo(id=int(hwnd), owner=owner, title=title_buf.value)

    # The process' executable name without its extension, or None if it can't be queried (protected process...).
    def _process_name(self, pid: int) -> str | None:
        handle = self._kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            if not self._kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.pointer(size)):
                return None
            return ntpath.splitext(ntpath.basename(buf.value))[0] or None
        finally:
            self._kernel32.CloseHandle(handle)

    # Owner fallback when the process name can't be queried: distinct from the title, unlike it would be.
    def _class_name(self, hwnd: int) -> str | None:
        buf = ctypes.create_unicode_buffer(256)
        return buf.value if self._user32.GetClassNameW(hwnd, buf, 256) else None

    def _print_window(self) -> Image.Image:
        user32, gdi32 = self._user32, self._gdi32
        hwnd = self._hwnd
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.pointer(rect)):
            raise CaptureError(f"Window '{self.window_label}' is gone: was it closed?")
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise CaptureError(f"Window '{self.window_label}' has no visible content (minimized?).")

        window_dc = user32.GetWindowDC(hwnd)
        if not window_dc:
            raise CaptureError("Could not get the window's device context.")
        mem_dc = bitmap = None
        try:
            mem_dc = gdi32.CreateCompatibleDC(window_dc)
            bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
            gdi32.SelectObject(mem_dc, bitmap)
            if not user32.PrintWindow(hwnd, mem_dc, _PW_RENDERFULLCONTENT):
                raise CaptureError(f"Could not capture window '{self.window_label}' (minimized, or a protected app).")
            return self._bitmap_to_image(mem_dc, bitmap, width, height)
        finally:
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, window_dc)

    def _bitmap_to_image(self, mem_dc, bitmap, width: int, height: int) -> Image.Image:
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # negative: top-down DIB, so rows don't come out flipped
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = _BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        if not self._gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.pointer(info), 0):
            raise CaptureError("Could not read the captured image")
        return Image.frombuffer("RGBA", (width, height), buffer.raw, "raw", "BGRA", width * 4, 1).convert("RGB")
