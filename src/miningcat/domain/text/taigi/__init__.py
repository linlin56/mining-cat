"""Taiwanese Hokkien (Taigi) writing systems: Hanji (漢字), Tâi-lô (the Ministry of Education's romanization) and
Pe̍h-ōe-jī (POJ, the church romanization), and the conversions between them."""
from miningcat.domain.text.taigi.hanji import annotate, convert, reading, romanize, to_hanji, tokenize
from miningcat.domain.text.taigi.ocr_repair import repair_ocr
from miningcat.domain.text.taigi.romanization import (
    LABELS,
    SYSTEMS,
    Syllable,
    detect,
    parse_syllable,
    parse_word,
    reading_key,
    respell,
    write_syllable,
    write_word,
)
from miningcat.domain.text.taigi.speech_text import alignment_letters, tts_text

__all__ = [
    "SYSTEMS", "LABELS", "Syllable", "parse_syllable", "parse_word", "write_syllable", "write_word", "reading_key",
    "respell", "detect", "convert", "romanize", "to_hanji", "reading", "annotate", "tokenize", "repair_ocr",
    "alignment_letters", "tts_text",
]
