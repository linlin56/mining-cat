from miningcat.domain.languages.study_language import CHINESE_LANGUAGES, NO_SPACE_LANGUAGES


def language_key(tag: str | None) -> str:
    """Maps a book or BCP-47 tag (zh-Hant, zh-TW, yue-HK, ja-JP...) to a study language key."""
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


def same_family(a: str, b: str) -> bool:
    """Whether a text tagged `a` may belong to `b`: book detection can't tell Mandarin from Cantonese."""
    return a == b or (a in CHINESE_LANGUAGES and b in CHINESE_LANGUAGES)
