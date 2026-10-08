import sys
from contextlib import nullcontext
from pathlib import Path

from PIL import Image

from language import Language


class OcrEngine:
    # `vertical`: comics and manga. On macOS, Apple Live Text reads vertical columns (Apple Vision skips them),
    # but only on the main thread of its process: see ocr_mining/worker.py.
    def __init__(self, language: Language, vertical: bool = False):
        self._language = language
        self._impl = _build_impl(language.value.ocr_lang_apple, language.value.ocr_lang_easyocr, vertical=vertical)
        self._latin_impl = None  # built at the first Latin line: see _reread_latin_lines

    # `image` is a file path or an in-memory PIL image (game / screen share OCR never touches the disk).
    # `drop_narrow_lines` is the hardsubs heuristic below: disable it when every line matters (e.g. a game dialog box).
    def read_text(self, image: Path | str | Image.Image, drop_narrow_lines: bool = True) -> str:
        # owocr's engines check `isinstance(img, Path)` internally : a plain str is rejected.
        if not isinstance(image, Image.Image):
            image = Path(image)
        success, result = self._recognize(image)
        if not success:
            return ""
        return _flatten_text(result, drop_narrow_lines=drop_narrow_lines)

    # Every line read, with its box in pixels (top-left origin): (text, x, y, width, height).
    def read_lines(self, image: Path | str | Image.Image) -> list[tuple[str, float, float, float, float]]:
        if not isinstance(image, Image.Image):
            image = Path(image)
        with Image.open(image) if isinstance(image, Path) else nullcontext(image) as img:
            width, height = img.size
            success, result = self._recognize(img)
        if not success:
            return []
        lines = []
        for paragraph in result.paragraphs:
            for line in paragraph.lines:
                text = line.text or "".join(w.text for w in line.words)
                b = line.bounding_box
                if text:
                    lines.append((text, b.left * width, b.top * height, b.width * width, b.height * height))
        return lines


    def _recognize(self, image: Path | Image.Image):
        success, result = self._impl(image)
        if success and self._language.value.ocr_lang_apple_latin:
            self._reread_latin_lines(image, result)
        return success, result

    # A language also written in Latin letters (Taigi's Tâi-lô and POJ): the CJK model reads their letters but drops
    # every tone mark (and reads ó as 6), so its Latin lines are read again, cropped, by a Latin model.
    def _reread_latin_lines(self, image: Path | Image.Image, result) -> None:
        lines = [line for paragraph in result.paragraphs for line in paragraph.lines if _is_latin(line.text or "")]
        if not lines:
            return
        if self._latin_impl is None:
            config = self._language.value
            self._latin_impl = _build_impl(config.ocr_lang_apple_latin, config.ocr_lang_easyocr_latin, latin=True)
        repair = _LATIN_REPAIRS.get(self._language.name, lambda text: text)
        with Image.open(image) if isinstance(image, Path) else nullcontext(image) as img:
            width, height = img.size
            for line in lines:
                b = line.bounding_box
                # tone marks stand above the letters, sometimes outside the CJK model's box
                pad_x, pad_y = b.height * 0.5, b.height * 0.6
                box = (max(0, (b.left - pad_x) * width), max(0, (b.top - pad_y) * height),
                       min(width, (b.left + b.width + pad_x) * width), min(height, (b.top + b.height + pad_y) * height))
                success, latin = self._latin_impl(img.crop(tuple(round(v) for v in box)).convert("RGB"))
                reread = [l for p in latin.paragraphs for l in p.lines if l.text] if success else []
                if reread:
                    # the widest line: the crop may catch a bit of the lines around it
                    line.text = repair(max(reread, key=lambda l: l.bounding_box.width).text)
                else:
                    line.text = repair(line.text)


def _is_latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isascii() or "\u00c0" <= c <= "\u024f" for c in letters) * 2 > len(letters)


def _repair_taigi(text: str) -> str:
    from mining import taigi
    return taigi.repair_ocr(text)


# Language name -> the fix of what its Latin model reads (look-alike tone marks...).
_LATIN_REPAIRS = {"TAIGI": _repair_taigi}


# `latin`: a model for the Latin lines of a CJK language, which mustn't "correct" them into words of its language.
def _build_impl(apple_language: str, easyocr_language: str, vertical: bool = False, latin: bool = False):
    if sys.platform == "darwin" and vertical:
        impl = _apple_live_text(apple_language)
        if impl is not None:
            return impl
    if sys.platform == "darwin":
        from owocr.ocr import AppleVision
        _ensure_owocr_objc_global()
        impl = AppleVision(language=apple_language, config={"language_correction": not latin})
        if getattr(impl, "available", False):
            return impl
        print("  Apple Vision unavailable on this system, falling back to EasyOCR")

    from owocr.ocr import EasyOCR
    impl = EasyOCR(config={}, language=easyocr_language)
    if not getattr(impl, "available", False):
        raise RuntimeError(
            "No usable OCR engine available (macOS 13+ is needed for Apple Vision, "
            "or install 'owocr[easyocr]' for the cross-platform fallback)."
        )
    return impl


# Apple Live Text (VisionKit, macOS 13+): owocr expects its private classes to be loaded already.
def _apple_live_text(language: str):
    try:
        import objc
        objc.loadBundle("VisionKit", {}, bundle_path="/System/Library/Frameworks/VisionKit.framework")
        from owocr.ocr import AppleLiveText
        impl = AppleLiveText(language=language)
    except Exception as exc:
        print(f"  Apple Live Text unavailable ({exc}), falling back to Apple Vision")
        return None
    return impl if getattr(impl, "available", False) else None


# Workaround for an owocr upstream bug (owocr==1.26.8)
# AppleVision.__call__ uses `objc.autorelease_pool()`, but AppleVision._import_dependencies() only imports `Vision` into owocr.ocr's module globals, never `objc`
# it silently works only when another owocr class (AppleLiveText) happens to have imported `objc` first as a side effect of owocr's own CLI/config flow.
# Since we instantiate AppleVision directly, we import `objc` ourselves and inject it the same way.
def _ensure_owocr_objc_global() -> None:
    import owocr.ocr as owocr_ocr_module
    if not hasattr(owocr_ocr_module, "objc"):
        import objc
        owocr_ocr_module.objc = objc


# Frames can contain both the actual subtitle line and unrelated on-screen text
# (e.g. staff/credits during an intro)
# Usually, subs are close to the widest detected line (spanning most of the crop), while credit/name blocks are narrow side columns
# so lines much narrower than the widest one are dropped instead of blindly joining everything.
# This might drop some legitimate subs that are unusually short, but it's a cheap filter that works well in practice.
_MIN_WIDTH_RATIO_OF_WIDEST_LINE = 0.6


def _flatten_text(ocr_result, drop_narrow_lines: bool = True) -> str:
    lines = [
        line
        for paragraph in ocr_result.paragraphs
        for line in paragraph.lines
        if line.text
    ]
    if not lines:
        return ""
    kept = lines
    if drop_narrow_lines:
        max_width = max(line.bounding_box.width for line in lines)
        kept = [line for line in lines if line.bounding_box.width >= _MIN_WIDTH_RATIO_OF_WIDEST_LINE * max_width]
    kept.sort(key=lambda line: line.bounding_box.center_y)
    return "\n".join(line.text for line in kept)
