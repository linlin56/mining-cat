import time
from dataclasses import dataclass
from typing import Callable

from PIL import Image

import chinese_converter
from game_ocr import capture
from game_ocr.capture import CaptureBackend, CaptureError
from game_ocr.settings import FULL_REGION, GameOcrSettings, Region
from language import Language
from ocr_mining import dedup, frames

# Languages written without spaces: lines wrapped by the game's dialog box are glued back together as-is.
_NO_SPACE_LANGUAGES = {Language.MANDARIN_TW, Language.MANDARIN_CN, Language.CANTONESE_HK, Language.JAPANESE}

# Below this length, a single different character is a different line (e.g. "はい" / "いい"), not OCR jitter.
_NEAR_DUPLICATE_MIN_LENGTH = 8


# Opens the backend of the current OS on the window saved in `settings`, without asking the user again.
# The backend state is saved back right away: Wayland portal restore tokens are single-use.
def open_saved_window(settings: GameOcrSettings, save: Callable[[GameOcrSettings], None] = GameOcrSettings.save) -> CaptureBackend:
    info = capture.backend_info()
    if not settings.has_window or info is None or settings.backend != info.id:
        raise CaptureError("No window selected yet: select the game window first.")
    backend = capture.create_backend()
    try:
        backend.restore(settings.backend_state)
    except Exception:
        backend.close()
        raise
    settings.backend_state = backend.state
    # The window may have been found back under a new title (macOS): keep the GUI's label in sync.
    settings.window_label = backend.window_label or settings.window_label
    save(settings)
    return backend


def crop_region(image: Image.Image, region: Region | None) -> Image.Image:
    x, y, w, h = frames.region_to_pixels(region or FULL_REGION, image.width, image.height)
    return image.crop((x, y, x + w, y + h))


# Returns (screenshot, text crop): the screenshot area of the frame, and the text area inside it.
def crop_areas(frame: Image.Image, screenshot_region: Region | None, text_region: Region | None) -> tuple[Image.Image, Image.Image]:
    screenshot = crop_region(frame, screenshot_region)
    return screenshot, crop_region(screenshot, text_region)


def join_lines(text: str, language: Language) -> str:
    separator = "" if language in _NO_SPACE_LANGUAGES else " "
    return separator.join(line.strip() for line in text.splitlines() if line.strip())


# Decides when the text area is worth an OCR pass, in automatic mode.
# Games often draw text progressively (typewriter effect): reading mid-animation would push half sentences,
# so the area must first stay the same between two polls, and differ from the last area that was read.
class ChangeDetector:
    def __init__(self, similar: Callable[[Image.Image, Image.Image], bool] = dedup.frames_are_similar):
        self._similar = similar
        self._last_seen: Image.Image | None = None
        self._last_read: Image.Image | None = None

    def should_read(self, crop: Image.Image) -> bool:
        previous, self._last_seen = self._last_seen, crop
        if previous is None or not self._similar(crop, previous):
            return False  # first poll, or still changing: wait until it settles
        if self._last_read is not None and self._similar(crop, self._last_read):
            return False  # settled, but already read
        self._last_read = crop
        return True


@dataclass
class CaptureResult:
    text: str
    screenshot: Image.Image
    ms: int


class GameOcrSession:
    def __init__(
        self,
        backend: CaptureBackend,
        settings: GameOcrSettings,
        language: Language,
        convert_target: str | None = None,
        join: bool = True,
        engine=None,
    ):
        self._backend = backend
        self._settings = settings
        self._language = language
        self._convert_source = chinese_converter.SCRIPT_FOR_LANGUAGE.get(language) if convert_target else None
        self._convert_target = convert_target
        self._join = join
        if engine is None:
            from ocr_mining.engine import OcrEngine
            engine = OcrEngine(language)
        self._engine = engine
        self._detector = ChangeDetector()
        self._last_text: str | None = None

    def grab(self) -> tuple[Image.Image, Image.Image]:
        return crop_areas(self._backend.grab_frame(), self._settings.screenshot_region, self._settings.text_region)

    def read(self, text_crop: Image.Image) -> str:
        # Every line of a dialog box matters: the hardsubs "drop narrow lines" heuristic would cut short last lines.
        text = self._engine.read_text(text_crop, drop_narrow_lines=False)
        if not dedup.is_plausible_text(text, self._language):
            return ""
        if self._join:
            text = join_lines(text, self._language)
        if self._convert_source is not None:
            text = chinese_converter.convert_text(text, self._convert_source, self._convert_target)
        return text.strip()

    # `force` (manual trigger) skips the change detection. Returns (result, "") or (None, reason it was skipped).
    def capture(self, force: bool = False) -> tuple[CaptureResult | None, str]:
        start = time.perf_counter()
        screenshot, text_crop = self.grab()
        if not force and not self._detector.should_read(text_crop):
            return None, "text area unchanged"
        text = self.read(text_crop)
        if not text:
            return None, "no text detected"
        if self._is_repeat(text):
            return None, "same text as the previous capture"
        self._last_text = text
        return CaptureResult(text=text, screenshot=screenshot, ms=round((time.perf_counter() - start) * 1000)), ""

    # Called when the page's history is cleared, so the current line can be captured again.
    def forget_last_text(self) -> None:
        self._last_text = None

    def _is_repeat(self, text: str) -> bool:
        last = self._last_text
        if last is None:
            return False
        if text == last:
            return True
        return min(len(text), len(last)) >= _NEAR_DUPLICATE_MIN_LENGTH and dedup.is_near_duplicate(text, last)
