from dataclasses import dataclass

from PIL import Image


class CaptureError(RuntimeError):
    pass


# A window MiningCat can capture, as listed by a backend that has no OS-provided picker (see CaptureBackend.has_system_picker).
@dataclass(frozen=True)
class WindowInfo:
    id: int
    owner: str
    title: str = ""

    @property
    def label(self) -> str:
        return f"{self.owner} - {self.title}" if self.title else self.owner


# Common interface of the OS-specific capture implementations (see capture/__init__.py for the per-OS switch).
# Lifecycle: select_window() the first time, or restore() from a previously saved `state`, then grab_frame() as often as needed, then close().
class CaptureBackend:
    # True when the OS shows its own window picker (e.g. the Wayland desktop portal) instead of MiningCat listing windows itself.
    has_system_picker: bool = False

    def list_windows(self) -> list[WindowInfo]:
        raise NotImplementedError

    # `window` comes from list_windows(), and is ignored by backends with a system picker (the OS asks the user instead).
    def select_window(self, window: WindowInfo | None = None) -> None:
        raise NotImplementedError

    # Reopens the window selected earlier without asking the user again (raises CaptureError if it's gone).
    def restore(self, state: dict) -> None:
        raise NotImplementedError

    # JSON-serializable data to persist so restore() can reopen the same window later.
    @property
    def state(self) -> dict:
        raise NotImplementedError

    # Human-readable name of the selected window, for the GUI / logs.
    @property
    def window_label(self) -> str:
        raise NotImplementedError

    # Latest image of the selected window, as an RGB PIL image.
    def grab_frame(self) -> Image.Image:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
