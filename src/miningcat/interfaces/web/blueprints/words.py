"""Word statuses, script and reading settings, and texts split into words to colour them."""
from flask import Blueprint, jsonify, request

from miningcat.application.mining import dictionaries, preferences, segmentation, words
from miningcat.domain.languages import CHINESE_LANGUAGES, LANGUAGES
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("words", __name__)

# A long chapter is a few hundred thousand characters at most.
SEGMENT_MAX_CHARS = 2_000_000


@bp.get("/api/mining/languages")
def api_languages():
    counts = words.counts()
    # a language is studied once it has a dictionary or saved words: only those get script settings
    studied = set(counts) | {d["language"] for d in dictionaries.list_dictionaries()}
    return jsonify(
        languages=[{"id": k, "name": v, "chinese": k in CHINESE_LANGUAGES, "studied": k in studied} for k, v in LANGUAGES.items()],
        scripts={lang: preferences.chinese_script_preference(lang) for lang in CHINESE_LANGUAGES},
        readings={"zh": preferences.reading_system("zh")},
        counts=counts,
    )


@bp.post("/api/mining/script")
def api_script():
    body = json_body()
    preferences.set_chinese_script_preference(study_language(body.get("language")), str(body.get("script")))
    return jsonify(ok=True)


@bp.post("/api/mining/reading")
def api_reading_system():
    body = json_body()
    preferences.set_reading_system(study_language(body.get("language")), str(body.get("system")))
    return jsonify(ok=True)


@bp.post("/api/words/status")
def api_word_status():
    body = json_body()
    language = study_language(body.get("language"))
    status = body.get("status")
    result = words.set_status(language, body.get("expression", ""), body.get("reading", ""),
                              None if status in (None, "new") else status)
    return jsonify(result)


@bp.get("/api/words")
def api_words():
    language = request.args.get("language")
    return jsonify(words=words.list_words(study_language(language) if language else None, request.args.get("status") or None,
                                          limit=min(int(request.args.get("limit", 500)), 5000)))


@bp.post("/api/words/statuses")
def api_word_statuses():
    body = json_body()
    expressions = body.get("expressions") or []
    if not isinstance(expressions, list):
        raise UserError("Error", "Expected a list of words.")
    return jsonify(statuses=words.statuses_for(study_language(body.get("language")), [str(e) for e in expressions[:20000]]))


@bp.post("/api/words/segment")
def api_segment():
    body = json_body()
    text = body.get("text")
    if not isinstance(text, str):
        raise UserError("Error", "Expected a text.")
    if len(text) > SEGMENT_MAX_CHARS:
        raise UserError("Error", f"Texts are limited to {SEGMENT_MAX_CHARS} characters.")
    return jsonify(segmentation.colour(study_language(body.get("language")), text))


