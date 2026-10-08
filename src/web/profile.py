from flask import Blueprint, jsonify, redirect, request

from miningcat.application.mining import preferences
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.domain.languages import CHINESE_LANGUAGES, LANGUAGES, NATIVE_NAMES

bp = Blueprint("profile", __name__)

SETTING = "study_language"

# Pages that need a language: without one, they send the user to the home page to choose it.
GUARDED_PREFIXES = ("/converter/", "/reader/", "/clipboard/", "/player/", "/settings/")


def current() -> str | None:
    language = settings.get(SETTING)
    return language if language in LANGUAGES else None


def set_current(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language!r}")
    settings.set(SETTING, language)


def _prefers_simplified(language: str) -> bool:
    return language in CHINESE_LANGUAGES and preferences.chinese_script_preference(language) == "simplified"


def converter_languages(language: str | None) -> list:
    """The converter's variants of a study language, the script the user learns first."""
    from miningcat.domain.languages import Language

    if not language:
        return []
    variants = Language.variants_of(language)
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
    from miningcat.application.mining import dictionaries, words

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
