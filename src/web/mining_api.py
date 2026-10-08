import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from miningcat.application import anki
from miningcat.application.mining import (
    dictionaries, frequency, lookup, preferences, segmentation, sentence_readings, sentence_tts, translation,
    word_audio, words,
)
from miningcat.domain.words.status import WordError
from miningcat.domain.languages import CHINESE_LANGUAGES, LANGUAGES, language_key, same_family

bp = Blueprint("mining", __name__)

# A long chapter is a few hundred thousand characters at most.
SEGMENT_MAX_CHARS = 2_000_000


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


@bp.errorhandler(WordError)
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
    body = _body()
    preferences.set_chinese_script_preference(_language(body.get("language")), str(body.get("script")))
    return jsonify(ok=True)


@bp.post("/api/mining/reading")
def api_reading_system():
    body = _body()
    preferences.set_reading_system(_language(body.get("language")), str(body.get("system")))
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


# Splits a text (a reader chapter) into dictionary words, with their status, to colour them.
@bp.post("/api/words/segment")
def api_segment():
    body = _body()
    text = body.get("text")
    if not isinstance(text, str):
        raise ApiError("Expected a text.")
    if len(text) > SEGMENT_MAX_CHARS:
        raise ApiError(f"Texts are limited to {SEGMENT_MAX_CHARS} characters.")
    return jsonify(segmentation.colour(_language(body.get("language")), text))


# ---------------------------------------------------------------- dictionaries

@bp.post("/api/dict/lookup")
def api_lookup():
    body = _body()
    text = str(body.get("text") or "")[:200]
    language = _language(body.get("language"))
    result = lookup.lookup(language, text)
    ranker = frequency.Ranker(language)
    for entry in result["entries"]:
        entry["display_reading"] = words.display_reading(language, entry.get("reading") or "")
        # rank in the frequency list of the language, shown in the popup and the card creator
        entry["frequency_rank"] = ranker.rank(entry["expression"], entry.get("form") or "")
    result["frequency"] = ranker.frontier
    return jsonify(result)


# The reading of every word of a card's sentence (HTML, the card's word in bold), chosen from the context.
@bp.post("/api/sentence/readings")
def api_sentence_readings():
    body = _body()
    sentence = str(body.get("sentence") or "")[:5000]
    return jsonify(sentence_readings.annotate(_language(body.get("language")), sentence, str(body.get("reading") or "")))


# ---------------------------------------------------------------- frequency list

@bp.get("/api/frequency/lists")
def api_frequency_lists():
    language = _language(request.args.get("language"))
    ref = frequency.reference(language)
    return jsonify(lists=frequency.lists(language), chosen=ref["id"] if ref else None, frontier=frequency.frontier(language),
                   limit_base=frequency.LIMIT_BASE, limit_per_known_word=frequency.LIMIT_PER_KNOWN_WORD)


@bp.post("/api/frequency/list")
def api_choose_frequency_list():
    body = _body()
    language = _language(body.get("language"))
    try:
        frequency.choose(language, int(body["id"]) if body.get("id") not in (None, "") else None)
    except (ValueError, TypeError) as exc:
        raise ApiError(str(exc), title="Frequency list")
    return jsonify(frontier=frequency.frontier(language))


# Online recordings of a word (JapanesePod101, Wiktionary, Lingua Libre), fetched when the user asks for them.
@bp.get("/api/dict/audio")
def api_word_audio():
    expression = str(request.args.get("expression") or "").strip()[:100]
    if not expression:
        raise ApiError("Missing word.")
    language = _language(request.args.get("language"))
    return jsonify(sources=word_audio.sources(language, expression, str(request.args.get("reading") or "")[:100]))


# Edge-TTS voices for a card's sentence audio, when the sentence has none.
@bp.get("/api/tts/voices")
def api_tts_voices():
    language = _language(request.args.get("language"))
    return jsonify(**sentence_tts.voices(language), chosen=sentence_tts.default_voice(language))


@bp.post("/api/tts")
def api_tts():
    import base64

    body = _body()
    try:
        audio = sentence_tts.synthesize(_language(body.get("language")), str(body.get("text") or ""), str(body.get("voice") or ""))
    except sentence_tts.TtsError as exc:
        raise ApiError(str(exc), title="Text-to-speech")
    return jsonify(data="data:audio/mpeg;base64," + base64.b64encode(audio).decode("ascii"), name="sentence.mp3")


# Offline translation of a card's sentence (Argos Translate), to the language chosen in the settings.
@bp.get("/api/translate/languages")
def api_translate_languages():
    return jsonify(languages=translation.targets(), chosen=translation.target_language())


@bp.post("/api/translate")
def api_translate():
    body = _body()
    try:
        translated = translation.translate(_language(body.get("language")), str(body.get("text") or ""),
                                           download=not body.get("prefetch"))
    except translation.TranslateError as exc:
        raise ApiError(str(exc), title="Translation")
    return jsonify(translation=translated, target=translation.target_language())


@bp.get("/api/translate/models")
def api_translate_models():
    return jsonify(translation.models())


@bp.post("/api/translate/models")
def api_download_translate_models():
    try:
        translation.start_download(_language(_body().get("language")))
    except translation.TranslateError as exc:
        raise ApiError(str(exc), title="Translation")
    return jsonify(translation.models())


@bp.post("/api/translate/models/<source>/<target>/delete")
def api_delete_translate_model(source: str, target: str):
    try:
        translation.delete_model(source, target)
    except translation.TranslateError as exc:
        raise ApiError(str(exc), title="Translation")
    return jsonify(translation.models())


@bp.get("/api/dict")
def api_dictionaries():
    return jsonify(dictionaries=dictionaries.list_dictionaries())


@bp.post("/api/dict/import")
def api_import_dictionary():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("Choose a dictionary file (.zip), or a frequency list (.json, .txt).")
    from web import profile

    # Dictionaries are imported for the language studied, unless the request names another.
    language = request.form.get("language") or profile.current() or ""
    if language and language not in LANGUAGES:
        raise ApiError(f"Unknown language: {language}")
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
        raise ApiError(f"“{info['title']}” looks like a {LANGUAGES.get(info['language'], info['language'])} dictionary, "
                       f"not a {LANGUAGES[language]} one. To import it, choose {LANGUAGES.get(info['language'], info['language'])} "
                       "on the home page first.", title="Wrong language")
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
                            str(body.get("tags") or ""), send=body.get("send", True) is not False,
                            key_reading=str(body.get("key_reading") or ""))
    return jsonify(card=card)


@bp.get("/api/cards")
def api_cards():
    language = request.args.get("language")
    return jsonify(cards=anki.list_cards(request.args.get("status") or None, language=_language(language) if language else None))


@bp.post("/api/cards/<int:card_id>/send")
def api_send_card(card_id: int):
    return jsonify(card=anki.send_card(card_id))


@bp.post("/api/cards/send-pending")
def api_send_pending():
    language = _body().get("language")
    return jsonify(anki.send_pending(_language(language) if language else None))


@bp.post("/api/cards/<int:card_id>/delete")
def api_delete_card(card_id: int):
    anki.delete_card(card_id)
    return jsonify(deleted=True)


@bp.post("/api/cards/export")
def api_export_cards():
    body = _body()
    ids = body.get("ids")
    if not ids and body.get("language"):
        language = _language(body["language"])
        ids = [c["id"] for status in ("pending", "failed") for c in anki.list_cards(status, 10_000, language=language)]
        if not ids:
            raise anki.AnkiError("There are no cards to export.")
    path = anki.export_apkg([int(i) for i in ids] if ids else None)
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/octet-stream")


@bp.get("/api/cards/media/<path:name>")
def api_card_media(name: str):
    base = anki.card_media_dir().resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ApiError("No such file.", 404)
    return send_file(path)
