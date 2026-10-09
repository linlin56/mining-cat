"""Subtitles and OCR text converted to another script: simplified / traditional Chinese characters (OpenCC), or
Taigi's writing systems (Hanji, Tâi-lô, POJ)."""
import re

from miningcat.domain.languages import Language
from miningcat.domain.text import chinese_script, taigi

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
    # Taigi: whatever the text is written in (Hanji, Tâi-lô, POJ or a mix), into one of them.
    "nan": [(taigi.LABELS[system], system) for system in taigi.SYSTEMS],
}
# Taigi isn't converted with OpenCC: "nan" stands for any of its writing systems.
TAIGI = "nan"


class ConversionError(ValueError):
    pass


def _taigi(source_script: str, target_script: str) -> bool:
    if source_script != TAIGI:
        return False
    if target_script not in taigi.SYSTEMS:
        raise ConversionError(f"No conversion path from {source_script!r} to {target_script!r}")
    return True


def can_convert(source_script: str, target_script: str) -> bool:
    return (source_script, target_script) in _CONFIGS or (source_script == TAIGI and target_script in taigi.SYSTEMS)


def convert_text(text: str, source_script: str, target_script: str) -> str:
    """A whole text (subtitles, OCR) from one Chinese script to another, quotation marks included."""
    if source_script == target_script:
        return text
    if _taigi(source_script, target_script):
        return taigi.convert(text, target_script)
    config = _CONFIGS.get((source_script, target_script))
    if config is None:
        raise ConversionError(f"No conversion path from {source_script!r} to {target_script!r}")
    converter = chinese_script.chinese_scripts.converter.converter(config)
    if converter is None:
        raise ConversionError("Converting Chinese characters needs OpenCC (pip install opencc-python-reimplemented).")
    return converter.convert(text).translate(str.maketrans(_QUOTES[(source_script, target_script)]))


# Index and timecode lines of an SRT file: Taigi's conversion leaves them as they are.
_SRT_CUE_LINE = re.compile(r"^\s*(\d+|[\d:,.]+ --> [\d:,.]+.*)\s*$")


def convert_srt(text: str, source_script: str, target_script: str) -> str:
    """The text of an SRT file in another script."""
    if _taigi(source_script, target_script):
        lines = text.split("\n")
        return "\n".join(line if _SRT_CUE_LINE.match(line) else convert_text(line, source_script, target_script)
                         for line in lines)
    return convert_text(text, source_script, target_script)


def whisper_script_target(language: Language) -> str | None:
    """Whisper's free transcription of Chinese languages often comes out in simplified characters, whatever the
    variant, since no reference text anchors the script (unlike an alignment on a book). This is the script it must
    be converted to (OpenCC's s2* conversions leave text already in the target script untouched), None when there's
    nothing to do."""
    canonical = language.profile.script
    if canonical == TAIGI:
        # Qwen3-ASR writes Taigi in Chinese characters, often simplified: Hanji are traditional, as in Taiwan.
        return "tw"
    return canonical if canonical not in (None, "s") else None
