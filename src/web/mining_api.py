# mining_api.py - HTTP API of the mining features: dictionaries, lookups, word statuses, card
# creator and Anki. Used by the reader's popup and by the Settings page.

import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from mining import anki, dictionaries, lookup, words
from mining.languages import CHINESE_LANGUAGES, LANGUAGES, language_key

bp = Blueprint("mining", __name__)


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, title: str = "Error"):
        super().__init__(message)
        self.message, self.status, self.title = message, status, title


@bp.errorhandler(ApiError)
def _api_error(exc: ApiError):
    return jsonify(title=exc.title, error=exc.message), exc.status


@bp.errorhandler(dictionaries.DictionaryError)
def _dict_error(exc):
    return jsonify(title="Dictionary", error=str(exc)), 400


@bp.errorhandler(words.WordError)
def _word_error(exc):
    return jsonify(title="Words", error=str(exc)), 400


@bp.errorhandler(anki.AnkiUnavailable)
def _anki_unavailable(exc):
    return jsonify(title="Anki isn't reachable", error=str(exc), unavailable=True), 503


@bp.errorhandler(anki.AnkiError)
def _anki_error(exc):
    return jsonify(title="Anki", error=str(exc)), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _language(value) -> str:
    language = language_key(str(value or ""))
    if language not in LANGUAGES:
        raise ApiError(f"Unknown language: {value!r}")
    return language


# ---------------------------------------------------------------- page

@bp.get("/settings/")
def settings_page():
    return render_template("settings.html")


# ---------------------------------------------------------------- languages & words

@bp.get("/api/mining/languages")
def api_languages():
    return jsonify(
        languages=[{"id": k, "name": v, "chinese": k in CHINESE_LANGUAGES} for k, v in LANGUAGES.items()],
        scripts={lang: words.chinese_script_preference(lang) for lang in CHINESE_LANGUAGES},
        counts=words.counts(),
    )


@bp.post("/api/mining/script")
def api_script():
    body = _body()
    words.set_chinese_script_preference(_language(body.get("language")), str(body.get("script")))
    return jsonify(ok=True)


@bp.post("/api/words/status")
def api_word_status():
    body = _body()
    language = _language(body.get("language"))
    status = body.get("status")
    result = words.set_status(language, body.get("expression", ""), body.get("reading", ""),
                              None if status in (None, "new") else status)
    return jsonify(result)


@bp.get("/api/words")
def api_words():
    language = request.args.get("language")
    return jsonify(words=words.list_words(_language(language) if language else None, request.args.get("status") or None,
                                          limit=min(int(request.args.get("limit", 500)), 5000)))


@bp.post("/api/words/statuses")
def api_word_statuses():
    body = _body()
    expressions = body.get("expressions") or []
    if not isinstance(expressions, list):
        raise ApiError("Expected a list of words.")
    return jsonify(statuses=words.statuses_for(_language(body.get("language")), [str(e) for e in expressions[:20000]]))


# ---------------------------------------------------------------- dictionaries

@bp.post("/api/dict/lookup")
def api_lookup():
    body = _body()
    text = str(body.get("text") or "")[:200]
    return jsonify(lookup.lookup(_language(body.get("language")), text))


@bp.get("/api/dict")
def api_dictionaries():
    return jsonify(dictionaries=dictionaries.list_dictionaries())


@bp.post("/api/dict/import")
def api_import_dictionary():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("Choose a dictionary file (.zip).")
    language = request.form.get("language") or ""
    if language and language not in LANGUAGES:
        raise ApiError(f"Unknown language: {language}")
    tmp = Path(tempfile.mkstemp(suffix=".zip", prefix="miningcat-dict-")[1])
    upload.save(tmp)
    try:
        info = dictionaries.inspect(tmp)
    except dictionaries.DictionaryError:
        tmp.unlink(missing_ok=True)
        raise
    if not language and not info["language"]:
        tmp.unlink(missing_ok=True)
        raise ApiError(f"Couldn't tell which language “{info['title']}” is for: choose it in the list and import it again.")
    job = dictionaries.start_import(tmp, language, upload.filename)
    return jsonify(job=job, title=info["title"], language=language or info["language"])


@bp.get("/api/dict/import/<job_id>")
def api_import_status(job_id: str):
    job = dictionaries.job_status(job_id)
    if job is None:
        raise ApiError("Unknown import.", 404)
    return jsonify(job)


@bp.post("/api/dict/<int:dict_id>")
def api_update_dictionary(dict_id: int):
    body = _body()
    return jsonify(dictionaries.update_dictionary(
        dict_id, enabled=body.get("enabled") if "enabled" in body else None,
        language=body.get("language") if "language" in body else None))


@bp.post("/api/dict/reorder")
def api_reorder_dictionaries():
    ids = _body().get("ids")
    if not isinstance(ids, list):
        raise ApiError("Expected a list of dictionary ids.")
    dictionaries.reorder([int(i) for i in ids])
    return jsonify(ok=True)


@bp.post("/api/dict/<int:dict_id>/delete")
def api_delete_dictionary(dict_id: int):
    dictionaries.delete_dictionary(dict_id)
    return jsonify(deleted=True)


@bp.get("/api/dict/<int:dict_id>/media/<path:ref>")
def api_dictionary_media(dict_id: int, ref: str):
    return send_file(dictionaries.media_path(dict_id, ref), max_age=86400)


# ---------------------------------------------------------------- Anki

@bp.get("/api/anki/status")
def api_anki_status():
    return jsonify(anki.status())


@bp.get("/api/anki/config")
def api_anki_config():
    return jsonify(config=anki.get_config(), card_fields=anki.CARD_FIELDS)


@bp.post("/api/anki/config")
def api_save_anki_config():
    return jsonify(config=anki.save_config(_body()))


@bp.get("/api/anki/fields")
def api_anki_fields():
    model = request.args.get("model", "")
    fields = anki.model_fields(model)
    return jsonify(fields=fields, guess=anki.guess_field_templates(fields))


@bp.post("/api/anki/sync")
def api_anki_sync():
    return jsonify(anki.sync())


@bp.post("/api/cards")
def api_create_card():
    body = _body()
    card = anki.create_card(_language(body.get("language")), body.get("fields") or {}, body.get("media") or {},
                            str(body.get("tags") or ""), send=body.get("send", True) is not False)
    return jsonify(card=card)


@bp.get("/api/cards")
def api_cards():
    return jsonify(cards=anki.list_cards(request.args.get("status") or None))


@bp.post("/api/cards/<int:card_id>/send")
def api_send_card(card_id: int):
    return jsonify(card=anki.send_card(card_id))


@bp.post("/api/cards/send-pending")
def api_send_pending():
    return jsonify(anki.send_pending())


@bp.post("/api/cards/<int:card_id>/delete")
def api_delete_card(card_id: int):
    anki.delete_card(card_id)
    return jsonify(deleted=True)


@bp.post("/api/cards/export")
def api_export_cards():
    ids = _body().get("ids")
    path = anki.export_apkg([int(i) for i in ids] if ids else None)
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/octet-stream")


@bp.get("/api/cards/media/<path:name>")
def api_card_media(name: str):
    base = anki.card_media_dir().resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ApiError("No such file.", 404)
    return send_file(path)
