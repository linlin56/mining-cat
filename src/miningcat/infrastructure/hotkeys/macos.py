import signal
import threading
from typing import Callable

from miningcat.infrastructure.hotkeys.base import Hotkey, HotkeyError

# This is displayed if the user hasn't granted Input Monitoring permission yet
# (or if the hotkey can't be registered for some reason.)
MACOS_PERMISSION_HINT = (
    "The capture key needs the Input Monitoring permission.\n"
    "Open System Settings > Privacy & Security > Input Monitoring, "
    "enable the app you launched MiningCat from (Terminal, iTerm2, VS Code...), then restart that app."
)

# Virtual key codes (Carbon's kVK_F1...kVK_F12)
_MACOS_KEYCODES = {
    "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97,
    "F7": 98, "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111,
}


class MacOSHotkey(Hotkey):
    def __init__(self, key: str):
        super().__init__(key)
        import Quartz
        self._Quartz = Quartz
        self._keycode = _MACOS_KEYCODES[key]
        self._tap = None
        self._run_loop = None

    def start(self, on_press: Callable[[], None], capture_url: str) -> None:
        Q = self._Quartz
        if not Q.CGPreflightListenEventAccess():
            # Shows the system prompt the first time only.
            Q.CGRequestListenEventAccess()
            raise HotkeyError(MACOS_PERMISSION_HINT)

        def callback(_proxy, event_type, event, _refcon):
            if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                Q.CGEventTapEnable(self._tap, True)  # macOS disables slow taps: turn it back on
            elif (event_type == Q.kCGEventKeyDown
                  and Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode) == self._keycode
                  and not Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat)):
                on_press()
            return event

        # Listen-only: the key still reaches the game.
        self._tap = Q.CGEventTapCreate(
            Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
            Q.CGEventMaskBit(Q.kCGEventKeyDown), callback, None,
        )
        if self._tap is None:
            raise HotkeyError(MACOS_PERMISSION_HINT)

        ready = threading.Event()

        def run():
            # Leaves SIGTERM/SIGINT to the main thread: delivered to this run loop, they never reach the server's loop,
            # and the Stop button had to kill the process.
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            self._run_loop = Q.CFRunLoopGetCurrent()
            source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            Q.CFRunLoopAddSource(self._run_loop, source, Q.kCFRunLoopCommonModes)
            Q.CGEventTapEnable(self._tap, True)
            ready.set()
            Q.CFRunLoopRun()

        threading.Thread(target=run, daemon=True, name="game-ocr-hotkey").start()
        ready.wait(timeout=5)

    def stop(self) -> None:
        if self._run_loop is not None:
            self._Quartz.CFRunLoopStop(self._run_loop)
            self._run_loop = None
        if self._tap is not None:
            self._Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None


