from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.text import taigi
from miningcat.domain.text.chinese_script import chinese_script, to_simplified, to_traditional
from miningcat.domain.text.zhuyin import is_zhuyin, pinyin_to_zhuyin, zhuyin_to_pinyin

# The Chinese script a user learns.
SCRIPTS = ("traditional", "simplified", "both")
# How readings are shown in the popup and written on cards: Mandarin in pinyin or zhuyin, Taigi in Tâi-lô or
# Pe̍h-ōe-jī. Words stay identified by their pinyin / Tâi-lô reading. The first system is the default.
READING_SYSTEMS = {"zh": ("pinyin", "zhuyin"), "nan": ("tailo", "poj")}


def preferred_form(language: str, expression: str, preference: str) -> str:
    """The form under which a word is saved, given the script the user learns."""
    if language not in CHINESE_LANGUAGES:
        return expression
    script = chinese_script(expression)
    # A word written the same way in both scripts (了解, 台灣's 台...) is kept as it is.
    if preference == "traditional" and script in ("simplified", "mixed"):
        return to_traditional(expression, language)
    if preference == "simplified" and script in ("traditional", "mixed"):
        return to_simplified(expression, language)
    return expression


def display_reading(language: str, expression: str, reading: str, system: str) -> str:
    """The reading in the system the user chose (zhuyin or pinyin, Tâi-lô or POJ), whichever the dictionary uses."""
    if reading and language == "zh":
        if system == "zhuyin":
            return pinyin_to_zhuyin(reading) or reading
        if is_zhuyin(reading):
            return zhuyin_to_pinyin(reading) or reading
    if language == "nan":
        if reading and reading != expression:
            return taigi.respell(reading, system)
        # a Hanji dictionary without readings: taibun's
        return taigi.reading(expression, system) or reading
    return reading
