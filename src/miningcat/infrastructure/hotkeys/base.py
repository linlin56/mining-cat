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
