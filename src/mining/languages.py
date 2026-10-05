# languages.py - Language helpers shared by lookups, words and cards.
#
# Words and dictionaries are keyed by a short language code: "zh" (Mandarin, both scripts),
# "yue" (Cantonese), "ja", "ko", "fr"... The script of Chinese text (traditional/simplified) is not
# part of the key: 説 and 说 are simply two different expressions, linked for display.

import re
import unicodedata

LANGUAGES = {
    "zh": "Mandarin",
    "yue": "Cantonese",
    "ja": "Japanese",
    "ko": "Korean",
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "vi": "Vietnamese",
    "ru": "Russian",
    "nan": "Taiwanese Hokkien (Taigi)",
}

# Languages written without spaces between words: a lookup tries every substring from the cursor.
NO_SPACE_LANGUAGES = {"zh", "yue", "ja", "nan"}
CHINESE_LANGUAGES = {"zh", "yue", "nan"}

_HIRAGANA = re.compile(r"[ぁ-ゖ]")
_KATAKANA = re.compile(r"[ァ-ヶ]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯]")
_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_PINYIN_TONE = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]|[a-z]+[1-5]\b", re.IGNORECASE)
_JYUTPING = re.compile(r"\b[a-z]{1,6}[1-6]\b")


def language_key(tag: str | None) -> str:
    """Maps a book or BCP-47 tag (zh-Hant, zh-TW, yue-HK, ja-JP...) to a language key."""
    tag = (tag or "").strip().lower()
    if not tag or tag == "und":
        return ""
    if tag.startswith(("yue", "zh-yue")):
        return "yue"
    if tag.startswith(("nan", "zh-min-nan")):
        return "nan"
    if tag.startswith(("zh", "cmn")):
        return "zh"
    return tag.split("-")[0]


def is_no_space(language: str) -> bool:
    return language in NO_SPACE_LANGUAGES


# ---------------------------------------------------------------- text variants

def katakana_to_hiragana(text: str) -> str:
    return _KATAKANA.sub(lambda m: chr(ord(m.group()) - 0x60), text)


def hiragana_to_katakana(text: str) -> str:
    return _HIRAGANA.sub(lambda m: chr(ord(m.group()) + 0x60), text)


_HALF_WIDTH_KANA = re.compile(r"[｡-ﾟ]+")


def _half_width_kana(text: str) -> str:
    # NFKC turns half-width katakana into full width, voicing marks included (ｶﾞ -> ガ).
    return _HALF_WIDTH_KANA.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)


_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})


def text_variants(text: str, language: str) -> list[str]:
    """Spellings a dictionary may use for `text` (like Yomitan's text preprocessors)."""
    text = unicodedata.normalize("NFC", text)
    variants = [text]
    if language == "ja":
        base = _half_width_kana(text)
        variants += [base, katakana_to_hiragana(base), hiragana_to_katakana(base)]
    elif language not in CHINESE_LANGUAGES and language != "ko":
        normalized = text.translate(_APOSTROPHES)
        variants += [normalized, normalized.lower()]
        if normalized[:1].isupper():
            variants.append(normalized[:1].lower() + normalized[1:])
    seen, unique = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def normalize_reading(reading: str, language: str) -> str:
    """Canonical reading used to identify a word (pinyin spacing and case vary between dictionaries)."""
    reading = unicodedata.normalize("NFC", reading or "").strip()
    if language in CHINESE_LANGUAGES:
        return re.sub(r"[\s・:'’-]", "", reading.lower())
    if language == "ja":
        return katakana_to_hiragana(reading)
    return reading


# ---------------------------------------------------------------- dictionary language guess

def guess_dictionary_language(samples: list[tuple[str, str]]) -> str:
    """Guesses the headword language of a dictionary from (expression, reading) samples."""
    text = " ".join(e for e, _ in samples)
    readings = " ".join(r for _, r in samples)
    if _KANA.search(text) or _KANA.search(readings):
        return "ja"
    if len(_HANGUL.findall(text)) > len(_HAN.findall(text)):
        return "ko"
    if len(_HAN.findall(text)) > len(text) * 0.3:
        if _PINYIN_TONE.search(readings):
            jyutping = len(_JYUTPING.findall(readings.lower()))
            tone_marks = len(re.findall(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]", readings))
            return "yue" if jyutping > tone_marks and re.search(r"[a-z]6\b", readings) else "zh"
        return "zh"
    return ""


# ---------------------------------------------------------------- Chinese scripts

_converters: dict[str, object] = {}


def _opencc(config: str):
    if config not in _converters:
        try:
            import opencc
            _converters[config] = opencc.OpenCC(config)
        except Exception:  # opencc missing or config unknown: no conversion
            _converters[config] = None
    return _converters[config]


def to_traditional(text: str) -> str:
    converter = _opencc("s2t")
    return converter.convert(text) if converter else text


def to_simplified(text: str) -> str:
    converter = _opencc("t2s")
    return converter.convert(text) if converter else text


def chinese_script(text: str) -> str:
    """'both' when the characters are the same in both scripts, else 'traditional' or 'simplified'."""
    simp, trad = to_simplified(text), to_traditional(text)
    if simp == trad == text:
        return "both"
    if text == trad:
        return "traditional"
    if text == simp:
        return "simplified"
    return "mixed"


def chinese_counterpart(text: str) -> tuple[str, str] | None:
    """The same word in the other script, e.g. 說 -> ('simplified', '说'); None if identical."""
    script = chinese_script(text)
    if script == "traditional":
        return "simplified", to_simplified(text)
    if script == "simplified":
        return "traditional", to_traditional(text)
    return None
