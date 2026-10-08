import ctypes
import threading
from ctypes import wintypes
from typing import Callable

from miningcat.infrastructure.hotkeys.base import Hotkey, HotkeyError

_WH_KEYBOARD_LL = 13
_WM_KEYDOWN = 0x0100
_WM_SYSKEYDOWN = 0x0104
_WM_QUIT = 0x0012

# Virtual key codes (winuser.h's VK_F1...VK_F12)
_WINDOWS_VK_CODES = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


# Declares argtypes/restypes: ctypes defaults to a 32-bit int otherwise, which overflows or truncates
# pointer-sized values (HHOOK, LPARAM...) on 64-bit Windows.
def _configure_winapi(user32) -> None:
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HMODULE, wintypes.DWORD]
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
    user32.CallNextHookEx.restype = ctypes.c_long
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class WindowsHotkey(Hotkey):
    def __init__(self, key: str):
        super().__init__(key)
        try:
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise HotkeyError(f"{exc}\nThe capture key needs the Windows API.") from exc
        _configure_winapi(self._user32)
        self._vk_code = _WINDOWS_VK_CODES[key]
        self._hook = None
        self._hook_ref = None  # keeps the ctypes callback alive: the hook stops firing once it's garbage collected
        self._thread_id: int | None = None

    def start(self, on_press: Callable[[], None], capture_url: str) -> None:
        user32 = self._user32
        hookproc_t = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        # Listen-only: the key still reaches the game (CallNextHookEx always forwards the event).
        def callback(code, wparam, lparam):
            if code == 0 and wparam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
                info = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if info.vkCode == self._vk_code:
                    on_press()
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._hook_ref = hookproc_t(callback)
        ready = threading.Event()
        errors: list[HotkeyError] = []

        # A low-level keyboard hook needs a message loop on the thread that installed it.
        def run():
            self._thread_id = self._kernel32.GetCurrentThreadId()
            self._hook = user32.SetWindowsHookExW(_WH_KEYBOARD_LL, self._hook_ref, None, 0)
            if not self._hook:
                errors.append(HotkeyError("Could not register the capture key (SetWindowsHookExW failed)."))
                ready.set()
                return
            ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        threading.Thread(target=run, daemon=True, name="game-ocr-hotkey").start()
        ready.wait(timeout=5)
        if errors:
            raise errors[0]

    def stop(self) -> None:
        if self._hook is not None:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
            self._thread_id = None


# Linux (GNOME), tested on Ubuntu 26

