"""The global key that triggers a video game capture, even with the game focused: one Hotkey per OS."""
import sys

from miningcat.infrastructure.hotkeys.base import DEFAULT_HOTKEY, HOTKEYS, Hotkey, HotkeyError


def create_hotkey(key: str, platform: str | None = None) -> Hotkey:
    platform = platform or sys.platform
    if platform == "darwin":
        from miningcat.infrastructure.hotkeys.macos import MacOSHotkey

        return MacOSHotkey(key)
    if platform == "linux":
        from miningcat.infrastructure.hotkeys.gnome import GnomeHotkey

        return GnomeHotkey(key)
    if platform == "win32":
        from miningcat.infrastructure.hotkeys.windows import WindowsHotkey

        return WindowsHotkey(key)
    raise HotkeyError(f"The capture key isn't supported on '{platform}' yet: use the page's capture button.")


__all__ = ["DEFAULT_HOTKEY", "HOTKEYS", "Hotkey", "HotkeyError", "create_hotkey"]
