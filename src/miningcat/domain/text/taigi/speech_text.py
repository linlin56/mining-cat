"""Taigi text as speech engines want it."""
import re
import unicodedata

from miningcat.domain.text.taigi.hanji import romanize
from miningcat.domain.text.taigi.romanization import NASAL


def alignment_letters(text: str) -> str:
    """The text as plain lower-case letters for a speech aligner (Hanji read as Tâi-lô, tones dropped):
    我欲食飯 -> "gua beh tsiah png"."""
    tailo = romanize(text, "tailo")
    plain = "".join(c for c in unicodedata.normalize("NFD", tailo) if not unicodedata.combining(c))
    plain = plain.replace(NASAL, "nn").lower()
    return " ".join(re.findall(r"[a-z]+", plain))


def tts_text(text: str) -> str:
    """The text in POJ with tone marks, how the MMS Taigi voice was trained (Bible recordings)."""
    return romanize(text, "poj")
