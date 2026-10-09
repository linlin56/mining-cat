import re
import unicodedata

_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_PINYIN_TONE = re.compile(r"[\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc]|[a-z]+[1-5]\b", re.IGNORECASE)
_TONE_MARK = re.compile(r"[\u0101\u00e1\u01ce\u00e0\u0113\u00e9\u011b\u00e8\u012b\u00ed\u01d0\u00ec\u014d\u00f3\u01d2\u00f2\u016b\u00fa\u01d4\u00f9\u01d6\u01d8\u01da\u01dc]")
_JYUTPING = re.compile(r"\b[a-z]{1,6}[1-6]\b")
# Spellings of Taigi romanizations that pinyin and jyutping don't have: the 8th tone's mark, POJ's o͘ and ⁿ,
# Tâi-lô's ts/tsh, aspirated kh/ph/th, and nasal vowels written -nn.
_TAIGI_READING = re.compile(r"\u030d|\u0358|\u207f|\bts|\b(?:kh|ph|th)[aeiou]|[aeiou]nn\b")


def guess_dictionary_language(samples: list[tuple[str, str]]) -> str:
    """Guesses the headword language of a dictionary from (expression, reading) samples ("" when unsure)."""
    text = " ".join(e for e, _ in samples)
    readings = " ".join(r for _, r in samples)
    if _KANA.search(text) or _KANA.search(readings):
        return "ja"
    if len(_HANGUL.findall(text)) > len(_HAN.findall(text)):
        return "ko"
    if len(_HAN.findall(text)) > len(text) * 0.3:
        taigi = len(_TAIGI_READING.findall(unicodedata.normalize("NFD", readings).lower()))
        if taigi >= max(3, len(samples) // 20):
            return "nan"
        if _PINYIN_TONE.search(readings):
            jyutping = len(_JYUTPING.findall(readings.lower()))
            tone_marks = len(_TONE_MARK.findall(readings))
            return "yue" if jyutping > tone_marks and re.search(r"[a-z]6\b", readings) else "zh"
        return "zh"
    return ""
