import sys
from pathlib import Path

from PIL import Image

from language import Language


class OcrEngine:
    def __init__(self, language: Language):
        self._impl = _build_impl(language)

    # `image` is a file path or an in-memory PIL image (game / screen share OCR never touches the disk).
    # `drop_narrow_lines` is the hardsubs heuristic below: disable it when every line matters (e.g. a game dialog box).
    def read_text(self, image: Path | str | Image.Image, drop_narrow_lines: bool = True) -> str:
        # owocr's engines check `isinstance(img, Path)` internally : a plain str is rejected.
        if not isinstance(image, Image.Image):
            image = Path(image)
        success, result = self._impl(image)
        if not success:
            return ""
        return _flatten_text(result, drop_narrow_lines=drop_narrow_lines)


def _build_impl(language: Language):
    if sys.platform == "darwin":
        from owocr.ocr import AppleVision
        _ensure_owocr_objc_global()
        impl = AppleVision(language=language.value.ocr_lang_apple)
        if getattr(impl, "available", False):
            return impl
        print("  Apple Vision unavailable on this system, falling back to EasyOCR")

    from owocr.ocr import EasyOCR
    impl = EasyOCR(config={}, language=language.value.ocr_lang_easyocr)
    if not getattr(impl, "available", False):
        raise RuntimeError(
            "No usable OCR engine available (macOS 13+ is needed for Apple Vision, "
            "or install 'owocr[easyocr]' for the cross-platform fallback)."
        )
    return impl


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
