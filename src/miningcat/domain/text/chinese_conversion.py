from miningcat.domain.languages import Language
from miningcat.domain.text import chinese_script

# OpenCC configuration per (source script, target script): s to tw, t or hk, and tw or hk to s.
_CONFIGS: dict[tuple[str, str], str] = {
    ("s", "tw"): "s2tw",
    ("s", "t"): "s2t",
    ("s", "hk"): "s2hk",
    ("tw", "s"): "tw2s",
    ("hk", "s"): "hk2s",
}

# OpenCC doesn't convert quotation marks: simplified mainland text uses “ ” ‘ ’, traditional text 「 」 『 』.
_TO_TRADITIONAL_QUOTES = {"“": "「", "”": "」", "‘": "『", "’": "』"}
_TO_SIMPLIFIED_QUOTES = {"「": "“", "」": "”", "『": "‘", "』": "’"}
_QUOTES: dict[tuple[str, str], dict[str, str]] = {
    ("s", "tw"): _TO_TRADITIONAL_QUOTES,
    ("s", "t"): _TO_TRADITIONAL_QUOTES,
    ("s", "hk"): _TO_TRADITIONAL_QUOTES,
    ("tw", "s"): _TO_SIMPLIFIED_QUOTES,
    ("hk", "s"): _TO_SIMPLIFIED_QUOTES,
}

# The scripts subtitles in each script can be converted to, with their label.
CONVERSION_TARGETS: dict[str, list[tuple[str, str]]] = {
    "s": [("Traditional - Taiwan", "tw"), ("Traditional - Chinese", "t")],
    "tw": [("Simplified - China", "s")],
    "hk": [("Simplified - China", "s")],
}


class ConversionError(ValueError):
    pass


def can_convert(source_script: str, target_script: str) -> bool:
    return (source_script, target_script) in _CONFIGS


def convert_text(text: str, source_script: str, target_script: str) -> str:
    """A whole text (subtitles, OCR) from one Chinese script to another, quotation marks included."""
    if source_script == target_script:
        return text
    config = _CONFIGS.get((source_script, target_script))
    if config is None:
        raise ConversionError(f"No conversion path from {source_script!r} to {target_script!r}")
    converter = chinese_script.chinese_scripts.converter.converter(config)
    if converter is None:
        raise ConversionError("Converting Chinese characters needs OpenCC (pip install opencc-python-reimplemented).")
    return converter.convert(text).translate(str.maketrans(_QUOTES[(source_script, target_script)]))


def whisper_script_target(language: Language) -> str | None:
    """Whisper's free transcription of Chinese languages often comes out in simplified characters, whatever the
    variant, since no reference text anchors the script (unlike an alignment on a book). This is the script it must
    be converted to (OpenCC's s2* conversions leave text already in the target script untouched), None when there's
    nothing to do."""
    canonical = language.profile.chinese_script
    return canonical if canonical not in (None, "s") else None
