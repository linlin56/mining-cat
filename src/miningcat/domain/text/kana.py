import re
import unicodedata

_HIRAGANA = re.compile(r"[\u3041-\u3096]")
_KATAKANA = re.compile(r"[\u30a1-\u30f6]")
_HALF_WIDTH_KANA = re.compile(r"[\uff61-\uff9f]+")


def katakana_to_hiragana(text: str) -> str:
    return _KATAKANA.sub(lambda m: chr(ord(m.group()) - 0x60), text)


def hiragana_to_katakana(text: str) -> str:
    return _HIRAGANA.sub(lambda m: chr(ord(m.group()) + 0x60), text)


def half_width_to_full_width_kana(text: str) -> str:
    # NFKC turns half-width katakana into full width, voicing marks included (ｶﾞ -> ガ).
    return _HALF_WIDTH_KANA.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)
