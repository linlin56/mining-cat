"""The language the user studies, chosen on the home page: the pages only show its books, videos and words."""
from miningcat.application.mining import dictionaries, preferences, words
from miningcat.domain.languages import CHINESE_LANGUAGES, LANGUAGES, NATIVE_NAMES, Language
from miningcat.infrastructure.persistence.settings_store import settings

SETTING = "study_language"


def current() -> str | None:
    language = settings.get(SETTING)
    return language if language in LANGUAGES else None


def set_current(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    settings.set(SETTING, language)


def _prefers_simplified(language: str) -> bool:
    return language in CHINESE_LANGUAGES and preferences.chinese_script_preference(language) == "simplified"


def converter_languages(language: str | None) -> list[Language]:
    """The converter's variants of a study language, the script the user learns first."""
    if not language:
        return []
    variants = Language.variants_of(language)
    if _prefers_simplified(language):
        variants.sort(key=lambda lang: lang is not Language.MANDARIN_CN)
    return variants


def tags(language: str | None) -> list[tuple[str, str]]:
    """(BCP-47 tag, label) of the forms a book or a video of the language can take, for their language setting."""
    if language == "zh":
        both = [("zh-Hant", "Traditional characters"), ("zh-Hans", "Simplified characters")]
        return both[::-1] if _prefers_simplified(language) else both
    if language == "yue":
        return [("yue-Hant", "Cantonese")]
    return [(language, LANGUAGES[language])] if language else []


def default_tag(language: str | None) -> str:
    """The tag of what the user adds while studying a language."""
    return tags(language)[0][0] if language else "und"


def describe(language: str | None) -> dict | None:
    if not language:
        return None
    return {
        "id": language,
        "name": LANGUAGES[language],
        "native": NATIVE_NAMES.get(language, ""),
        "chinese": language in CHINESE_LANGUAGES,
        "tag": default_tag(language),
        "tags": [{"tag": t, "label": label} for t, label in tags(language)],
        "converter": bool(converter_languages(language)),
    }


def overview() -> list[dict]:
    """Every study language, with the user's number of words and dictionaries."""
    counts = words.counts()
    dict_counts: dict[str, int] = {}
    for d in dictionaries.list_dictionaries():
        dict_counts[d["language"]] = dict_counts.get(d["language"], 0) + 1
    return [{
        **describe(key),
        "words": sum((counts.get(key) or {}).values()),
        "dictionaries": dict_counts.get(key, 0),
    } for key in LANGUAGES]
