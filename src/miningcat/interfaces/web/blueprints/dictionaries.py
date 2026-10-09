"""Dictionaries: lookups, imports and settings, and the frequency lists of each language."""
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from miningcat.application import study_language as studied
from miningcat.application.mining import dictionaries, frequency, lookup, words
from miningcat.domain.languages import LANGUAGES, same_family
from miningcat.domain.text.readings import reading_match
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("dictionaries", __name__)


@bp.post("/api/dict/lookup")
def api_lookup():
    body = json_body()
    text = str(body.get("text") or "")[:200]
    language = study_language(body.get("language"))
    # a known reading (a CSV's pinyin column): tells the entry of that pronunciation (還 huán, not hái)
    wanted = str(body.get("reading") or "").strip()[:100]
    result = lookup.lookup(language, text)
    ranker = frequency.Ranker(language)
    for entry in result["entries"]:
        entry["display_reading"] = words.display_reading(language, entry["expression"], entry.get("reading") or "")
        # rank in the frequency lists of the language (combined), shown in the popup and the card creator
        entry["frequency_rank"] = ranker.rank(entry["expression"], entry.get("form") or "")
        if wanted:
            entry["reading_match"] = reading_match(wanted, entry.get("reading") or "", language)
    result["frequency"] = ranker.frontier
    return jsonify(result)


@bp.get("/api/frequency/lists")
def api_frequency_lists():
    language = study_language(request.args.get("language"))
    chosen = [ref["id"] for ref in frequency.references(language)]
    return jsonify(lists=frequency.lists(language), chosen=chosen, frontier=frequency.frontier(language),
                   limit_base=frequency.LIMIT_BASE, limit_per_known_word=frequency.LIMIT_PER_KNOWN_WORD)


@bp.post("/api/frequency/list")
def api_choose_frequency_list():
    body = json_body()
    language = study_language(body.get("language"))
    try:
        # the lists combined for the recommendations, none to recommend every i+1 sentence
        frequency.choose(language, [int(i) for i in body.get("ids") or []])
    except (ValueError, TypeError) as exc:
        raise UserError("Frequency list", str(exc))
    return jsonify(frontier=frequency.frontier(language))


@bp.get("/api/dict")
def api_dictionaries():
    return jsonify(dictionaries=dictionaries.list_dictionaries())


@bp.post("/api/dict/import")
def api_import_dictionary():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise UserError("Error", "Choose a dictionary file (.zip), or a frequency list (.json, .txt).")
    # Dictionaries are imported for the language studied, unless the request names another.
    language = request.form.get("language") or studied.current() or ""
    if language and language not in LANGUAGES:
        raise UserError("Error", f"Unknown language: {language}")
    suffix = Path(upload.filename).suffix.lower()
    suffix = suffix if suffix in dictionaries.FREQUENCY_LIST_SUFFIXES else ".zip"
    tmp = Path(tempfile.mkstemp(suffix=suffix, prefix="miningcat-dict-")[1])
    upload.save(tmp)
    try:
        info = dictionaries.inspect(tmp, upload.filename)
    except dictionaries.DictionaryError:
        tmp.unlink(missing_ok=True)
        raise
    if language and info["language"] and not same_family(info["language"], language):
        tmp.unlink(missing_ok=True)
        found = LANGUAGES.get(info["language"], info["language"])
        raise UserError("Wrong language", f"“{info['title']}” looks like a {found} dictionary, not a {LANGUAGES[language]} "
                        f"one. To import it, choose {found} on the home page first.")
    if not language and not info["language"]:
        tmp.unlink(missing_ok=True)
        raise UserError("Error", f"Couldn't tell which language “{info['title']}” is for: choose it in the list and import it again.")
    job = dictionaries.start_import(tmp, language, upload.filename)
    return jsonify(job=job, title=info["title"], language=language or info["language"])


@bp.get("/api/dict/import/<job_id>")
def api_import_status(job_id: str):
    job = dictionaries.job_status(job_id)
    if job is None:
        raise UserError("Error", "Unknown import.", 404)
    return jsonify(job)


@bp.post("/api/dict/<int:dict_id>")
def api_update_dictionary(dict_id: int):
    body = json_body()
    return jsonify(dictionaries.update_dictionary(
        dict_id, enabled=body.get("enabled") if "enabled" in body else None,
        language=body.get("language") if "language" in body else None))


@bp.post("/api/dict/reorder")
def api_reorder_dictionaries():
    ids = json_body().get("ids")
    if not isinstance(ids, list):
        raise UserError("Error", "Expected a list of dictionary ids.")
    dictionaries.reorder([int(i) for i in ids])
    return jsonify(ok=True)


@bp.post("/api/dict/<int:dict_id>/delete")
def api_delete_dictionary(dict_id: int):
    dictionaries.delete_dictionary(dict_id)
    return jsonify(deleted=True)


@bp.get("/api/dict/<int:dict_id>/media/<path:ref>")
def api_dictionary_media(dict_id: int, ref: str):
    return send_file(dictionaries.media_path(dict_id, ref), max_age=86400)


