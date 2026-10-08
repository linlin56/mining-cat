import re
import unicodedata

from miningcat.domain.languages.study_language import CHINESE_LANGUAGES
from miningcat.domain.text import taigi
from miningcat.domain.text.kana import katakana_to_hiragana
from miningcat.domain.text.zhuyin import pinyin_to_zhuyin

_LATIN = re.compile(r"[A-Za-z]")


def normalize_reading(reading: str, language: str) -> str:
    """Canonical reading used to identify a word (pinyin spacing and case vary between dictionaries)."""
    reading = unicodedata.normalize("NFC", reading or "").strip()
    if language == "nan" and _LATIN.search(reading):
        reading = taigi.respell(reading, "tailo")  # a POJ reading is the Tâi-lô one
    if language in CHINESE_LANGUAGES:
        return re.sub(r"[\s・:'’-]", "", reading.lower())
    if language == "ja":
        return katakana_to_hiragana(reading)
    return reading


def reading_key(reading: str, language: str) -> str:
    """Key telling whether two dictionary readings are the same pronunciation: in Mandarin, pinyin with tone numbers
    (xing2), with tone marks (xíng) and zhuyin (ㄒㄧㄥˊ) are. Only for comparing dictionaries: saved words use
    normalize_reading."""
    if language == "zh":
        zhuyin = pinyin_to_zhuyin(reading.replace("ɡ", "g"))  # the "ɡ" of 兩岸詞典's xínɡ
        if zhuyin:
            # the first tone may be written ˉ, and the neutral tone's dot before or after its syllable
            zhuyin = re.sub(r"[\sˉ]", "", zhuyin)
            return zhuyin.replace("˙", "") + "˙" * zhuyin.count("˙")
    if language == "nan":
        key = taigi.reading_key(reading)
        if key:
            return key
    return normalize_reading(reading, language)


def reading_match(reading: str, other: str, language: str) -> int:
    """How well two readings agree: 2 the same pronunciation, 1 the same syllables with other tones (Mandarin:
    an erhua or a neutral tone written another way), 0 not."""
    a, b = reading_key(reading, language), reading_key(other, language)
    if not a or not b:
        return 0
    if a == b:
        return 2
    if language == "zh":
        toneless = lambda key: re.sub(r"[ˊˇˋ˙]", "", key)
        return 1 if toneless(a) == toneless(b) else 0
    if language == "nan":  # the same syllables, with tone sandhi or a neutral tone written
        return 1 if re.sub(r"\d", "", a) == re.sub(r"\d", "", b) else 0
    return 0
