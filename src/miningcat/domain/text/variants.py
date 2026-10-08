import unicodedata

from miningcat.domain.languages.study_language import CHINESE_LANGUAGES
from miningcat.domain.text.kana import half_width_to_full_width_kana, hiragana_to_katakana, katakana_to_hiragana

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'"})


def text_variants(text: str, language: str) -> list[str]:
    """Spellings a dictionary may use for `text` (like Yomitan's text preprocessors)."""
    text = unicodedata.normalize("NFC", text)
    variants = [text]
    if language == "ja":
        base = half_width_to_full_width_kana(text)
        variants += [base, katakana_to_hiragana(base), hiragana_to_katakana(base)]
    elif language not in CHINESE_LANGUAGES and language != "ko":
        normalized = text.translate(_APOSTROPHES)
        variants += [normalized, normalized.lower()]
        if normalized[:1].isupper():
            variants.append(normalized[:1].lower() + normalized[1:])
    return list(dict.fromkeys(v for v in variants if v))
