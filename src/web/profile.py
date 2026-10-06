# profile.py - The language the user studies, chosen on the home page. Every screen then only shows
# what belongs to it: the converter's variants, the books and videos, dictionaries, words, Anki setup, cards.
#
# It's a mining language key ("zh", "yue", "ja"...), saved in the database's settings. The converter's
# languages (language.Language) are variants of it: Mandarin is Taiwan (traditional) or China (simplified).

from flask import Blueprint, jsonify, redirect, request

from mining import db
from mining.languages import CHINESE_LANGUAGES, LANGUAGES, language_key

bp = Blueprint("profile", __name__)

SETTING = "study_language"

NATIVE_NAMES = {
    "zh": "中文", "yue": "粵語", "nan": "台語", "ja": "日本語", "ko": "한국어", "en": "English",
    "fr": "Français", "de": "Deutsch", "es": "Español", "it": "Italiano", "pt": "Português",
    "pl": "Polski", "vi": "Tiếng Việt", "ru": "Русский",
}

# Pages that need a language: without one, they send the user to the home page to choose it.
GUARDED_PREFIXES = ("/converter/", "/reader/", "/player/", "/settings/")


def current() -> str | None:
    language = db.get_setting(SETTING)
    return language if language in LANGUAGES else None


def set_current(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    db.set_setting(SETTING, language)


def same_family(a: str, b: str) -> bool:
    """Whether a text tagged `a` may belong to `b`: book detection can't tell Mandarin from Cantonese."""
    return a == b or (a in CHINESE_LANGUAGES and b in CHINESE_LANGUAGES)


def _prefers_simplified(language: str) -> bool:
    from mining import words
    return language in CHINESE_LANGUAGES and words.chinese_script_preference(language) == "simplified"


def converter_languages(language: str | None) -> list:
    """The converter's variants of a study language, the script the user learns first."""
    from language import Language
    from web.game import language_tag

    if not language:
        return []
    variants = [lang for lang in Language if language_key(language_tag(lang)) == language]
    if _prefers_simplified(language):
        variants.sort(key=lambda lang: lang is not Language.MANDARIN_CN)
    return variants


# (BCP-47 tag, label) of the forms a book or a video of the language can take, for their language setting.
def tags(language: str | None) -> list[tuple[str, str]]:
    if language == "zh":
        both = [("zh-Hant", "Traditional characters"), ("zh-Hans", "Simplified characters")]
        return both[::-1] if _prefers_simplified(language) else both
    if language == "yue":
        return [("yue-Hant", "Cantonese")]
    return [(language, LANGUAGES[language])] if language else []


def default_tag(language: str | None) -> str:
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


def guard():
    """before_request hook: pages of a language need one."""
    if request.method == "GET" and request.path.startswith(GUARDED_PREFIXES) and "/api/" not in request.path:
        if current() is None:
            return redirect(f"/?next={request.path}")
    return None


@bp.get("/api/profile")
def api_profile():
    from mining import dictionaries, words

    counts = words.counts()
    dict_counts: dict[str, int] = {}
    for d in dictionaries.list_dictionaries():
        dict_counts[d["language"]] = dict_counts.get(d["language"], 0) + 1
    return jsonify(
        current=describe(current()),
        languages=[{
            **describe(key),
            "words": sum((counts.get(key) or {}).values()),
            "dictionaries": dict_counts.get(key, 0),
        } for key in LANGUAGES],
    )


@bp.post("/api/profile")
def api_set_profile():
    body = request.get_json(silent=True) or {}
    try:
        set_current(str(body.get("language") or ""))
    except ValueError as exc:
        return jsonify(title="Language", error=str(exc)), 400
    return jsonify(current=describe(current()))
