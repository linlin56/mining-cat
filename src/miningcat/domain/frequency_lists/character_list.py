"""Kanji Grid character lists: the characters of a text, most frequent first, in groups of a thousand."""
from collections import Counter

from miningcat.domain.languages import Language


def supports_language(language: Language) -> bool:
    """Character lists (Kanji Grid) are only made for languages written with Chinese characters."""
    return language.profile.character_list is not None


def compute(text: str, language: Language) -> Counter:
    character_list = language.profile.character_list
    if character_list is None:
        supported = [lang.profile.label for lang in Language if supports_language(lang)]
        raise ValueError(
            f"character_frequency does not support {language.profile.label}. Supported: {', '.join(supported)}"
        )
    return Counter(character_list.characters.findall(text))


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
        "lang": language.profile.character_list.tag,
        "leftover_group": "Not in book",
        "groups": groups,
    }
