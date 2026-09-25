import ast
import shutil
import subprocess
import sys
import threading
from typing import Callable

HOTKEYS: tuple[str, ...] = tuple(f"F{i}" for i in range(1, 13))
DEFAULT_HOTKEY = "F9"

class HotkeyError(RuntimeError):
    pass

class Hotkey:
    def __init__(self, key: str):
        if key not in HOTKEYS:
            raise HotkeyError(f"Unsupported capture key '{key}' (supported: {', '.join(HOTKEYS)})")
        self.key = key

    # `on_press` is called from a background thread. `capture_url` is the URL a key press must POST to.
    def start(self, on_press: Callable[[], None], capture_url: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


# macOS section

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


# Linux (GNOME), tested on Ubuntu 26

_GNOME_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
_GNOME_LIST_KEY = "custom-keybindings"
_GNOME_BINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/miningcat/"
_GNOME_BINDING_SCHEMA = f"{_GNOME_SCHEMA}.custom-keybinding:{_GNOME_BINDING_PATH}"

_GNOME_HINT = (
    "The capture key uses a GNOME custom shortcut (gsettings), which isn't available here.\n"
    "Bind your own global shortcut to this command instead: curl -s -X POST {url}"
)


def _parse_gsettings_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("@as "):  # typed empty array: "@as []"
        value = value[len("@as "):]
    parsed = ast.literal_eval(value)
    return [str(v) for v in parsed]


class GnomeHotkey(Hotkey):
    def __init__(self, key: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run):
        super().__init__(key)
        self._run = run
        self._registered = False

    def _gsettings(self, *args: str) -> str:
        result = self._run(["gsettings", *args], capture_output=True, text=True, check=True)
        return result.stdout

    def _bindings(self) -> list[str]:
        return _parse_gsettings_list(self._gsettings("get", _GNOME_SCHEMA, _GNOME_LIST_KEY))

    def _set_bindings(self, paths: list[str]) -> None:
        self._gsettings("set", _GNOME_SCHEMA, _GNOME_LIST_KEY, str(paths))

    # The GNOME shortcut runs curl itself: `on_press` isn't needed.
    def start(self, on_press: Callable[[], None], capture_url: str) -> None:
        if shutil.which("gsettings") is None or shutil.which("curl") is None:
            raise HotkeyError(_GNOME_HINT.format(url=capture_url))
        try:
            paths = self._bindings()
            if _GNOME_BINDING_PATH not in paths:
                self._set_bindings(paths + [_GNOME_BINDING_PATH])
            self._gsettings("set", _GNOME_BINDING_SCHEMA, "name", "MiningCat capture")
            self._gsettings("set", _GNOME_BINDING_SCHEMA, "command", f"curl -s -X POST {capture_url}")
            self._gsettings("set", _GNOME_BINDING_SCHEMA, "binding", self.key)
        except (subprocess.CalledProcessError, ValueError, SyntaxError) as exc:
            raise HotkeyError(f"Could not register the GNOME shortcut: {exc}\n" + _GNOME_HINT.format(url=capture_url)) from exc
        self._registered = True

    # Removes the shortcut, so the key goes back to normal when MiningCat doesn't capture.
    def stop(self) -> None:
        if not self._registered:
            return
        self._registered = False
        try:
            self._set_bindings([p for p in self._bindings() if p != _GNOME_BINDING_PATH])
            for key in ("name", "command", "binding"):
                self._gsettings("reset", _GNOME_BINDING_SCHEMA, key)
        except (subprocess.CalledProcessError, ValueError, SyntaxError):
            pass


def create_hotkey(key: str, platform: str | None = None) -> Hotkey:
    platform = platform or sys.platform
    if platform == "darwin":
        return MacOSHotkey(key)
    if platform == "linux":
        return GnomeHotkey(key)
    raise HotkeyError(f"The capture key isn't supported on '{platform}' yet: use the page's capture button.")
