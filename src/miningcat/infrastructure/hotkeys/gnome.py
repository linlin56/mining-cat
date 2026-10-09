import ast
import shutil
import subprocess
from typing import Callable

from miningcat.infrastructure.hotkeys.base import Hotkey, HotkeyError

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


