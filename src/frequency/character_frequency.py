import json
import re
from collections import Counter
from pathlib import Path

from language import Language


_CHAR_PATTERN: dict[Language, re.Pattern] = {
    Language.MANDARIN_TW: re.compile(r"[一-鿿㐀-䶿]"),
    Language.MANDARIN_CN: re.compile(r"[一-鿿㐀-䶿]"),
    # Kanji (CJK + Extension A) + hiragana + katakana
    Language.JAPANESE: re.compile(r"[一-鿿㐀-䶿぀-ゟ゠-ヿ]"),
}

_LANG_CODE: dict[Language, str] = {
    Language.MANDARIN_TW: "zh-Hant",
    Language.MANDARIN_CN: "zh-Hans",
    Language.JAPANESE: "ja",
}

SUPPORTED_LANGUAGES: frozenset[Language] = frozenset(_CHAR_PATTERN)


def supports_language(language: Language) -> bool:
    return language in SUPPORTED_LANGUAGES


def compute(text: str, language: Language) -> Counter:
    if language not in _CHAR_PATTERN:
        raise ValueError(
            f"character_frequency does not support {language.value.label}. "
            f"Supported: {', '.join(l.value.label for l in SUPPORTED_LANGUAGES)}"
        )
    return Counter(_CHAR_PATTERN[language].findall(text))


def build_json(name: str, language: Language, counter: Counter, group_size: int = 1000) -> dict:
    sorted_chars = [ch for ch, _ in counter.most_common()]
    groups = []
    for i in range(0, len(sorted_chars), group_size):
        group_chars = sorted_chars[i: i + group_size]
        rank = i + group_size
        groups.append({
            "name": f"Top {rank // 1000}k characters",
            "characters": "".join(group_chars),
        })
    return {
        "version": 1,
        "name": name,
        "lang": _LANG_CODE[language],
        "leftover_group": "Not in book",
        "groups": groups,
    }


def save_json(data: dict, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
