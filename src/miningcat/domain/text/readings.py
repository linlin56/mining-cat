import re
import unicodedata

from miningcat.domain.languages.study_language import CHINESE_LANGUAGES
from miningcat.domain.text.kana import katakana_to_hiragana
from miningcat.domain.text.zhuyin import pinyin_to_zhuyin


def normalize_reading(reading: str, language: str) -> str:
    """Canonical reading used to identify a word (pinyin spacing and case vary between dictionaries)."""
    reading = unicodedata.normalize("NFC", reading or "").strip()
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
    return normalize_reading(reading, language)
