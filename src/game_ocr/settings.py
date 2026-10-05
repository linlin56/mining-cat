import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import GAME_OCR_SETTINGS
from game_ocr.hotkey import DEFAULT_HOTKEY

Region = tuple[float, float, float, float]

# Whole frame: the default of both areas (on macOS the capture already is exactly the window).
FULL_REGION: Region = (0.0, 0.0, 1.0, 1.0)


# What the user picked, persisted between runs (and between the GUI and the `game serve` subprocess).
# Areas are normalized (x, y, w, h) fractions, like the hardsubs OCR region, so they survive window resizes and Retina scaling:
# - screenshot_region: relative to the captured frame. It's the image sent to the web page.
#   On GNOME/Wayland the portal frame is screen-sized with the window pasted on black, so this crops the window borders.
# - text_region: relative to the screenshot area. It's the only part that goes through OCR.
@dataclass
class GameOcrSettings:
    backend: str | None = None  # id of the backend `backend_state` belongs to (see capture.BACKENDS)
    backend_state: dict = field(default_factory=dict)
    window_label: str = ""
    screenshot_region: Region | None = None
    text_region: Region | None = None
    # How captures are triggered: the capture key (default), or continuously when the text changes.
    hotkey: str = DEFAULT_HOTKEY
    continuous: bool = False

    @property
    def has_window(self) -> bool:
        return self.backend is not None and bool(self.backend_state)

    @property
    def is_ready(self) -> bool:
        return self.has_window and self.text_region is not None

    # Saved areas belong to the previous window: a newly selected window starts from scratch.
    def set_window(self, backend: str, state: dict, label: str) -> None:
        self.backend, self.backend_state, self.window_label = backend, state, label
        self.screenshot_region = None
        self.text_region = None

    # The text area is relative to the screenshot area, so it can't be kept when the latter changes.
    def set_screenshot_region(self, region: Region) -> None:
        if region != self.screenshot_region:
            self.text_region = None
        self.screenshot_region = region

    # `path` defaults to config.GAME_OCR_SETTINGS, looked up at call time so tests can redirect it.
    @classmethod
    def load(cls, path: Path | None = None) -> "GameOcrSettings":
        path = path or GAME_OCR_SETTINGS
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for key in ("screenshot_region", "text_region"):
            if known.get(key) is not None:
                known[key] = tuple(known[key])
        return cls(**known)

    def save(self, path: Path | None = None) -> None:
        path = path or GAME_OCR_SETTINGS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
