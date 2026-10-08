"""Tools of the card creator: readings of a sentence's words, word recordings, sentence audio and translation."""
import base64

from flask import Blueprint, jsonify, request

from miningcat.application.mining import sentence_readings, sentence_tts, translation, word_audio
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("sentence_tools", __name__)


@bp.post("/api/sentence/readings")
def api_sentence_readings():
    body = json_body()
    sentence = str(body.get("sentence") or "")[:5000]
    return jsonify(sentence_readings.annotate(study_language(body.get("language")), sentence, str(body.get("reading") or "")))




@bp.get("/api/dict/audio")
def api_word_audio():
    expression = str(request.args.get("expression") or "").strip()[:100]
    if not expression:
        raise UserError("Error", "Missing word.")
    language = study_language(request.args.get("language"))
    return jsonify(sources=word_audio.sources(language, expression, str(request.args.get("reading") or "")[:100]))


@bp.get("/api/tts/voices")
def api_tts_voices():
    language = study_language(request.args.get("language"))
    return jsonify(**sentence_tts.voices(language), chosen=sentence_tts.default_voice(language))


@bp.post("/api/tts")
def api_tts():
    body = json_body()
    try:
        audio = sentence_tts.synthesize(study_language(body.get("language")), str(body.get("text") or ""), str(body.get("voice") or ""))
    except sentence_tts.TtsError as exc:
        raise UserError("Text-to-speech", str(exc))
    return jsonify(data="data:audio/mpeg;base64," + base64.b64encode(audio).decode("ascii"), name="sentence.mp3")


@bp.get("/api/translate/languages")
def api_translate_languages():
    return jsonify(languages=translation.targets(), chosen=translation.target_language())


@bp.post("/api/translate")
def api_translate():
    body = json_body()
    try:
        translated = translation.translate(study_language(body.get("language")), str(body.get("text") or ""),
                                           download=not body.get("prefetch"))
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation=translated, target=translation.target_language())


@bp.get("/api/translate/models")
def api_translate_models():
    return jsonify(translation.models())


@bp.post("/api/translate/models")
def api_download_translate_models():
    try:
        translation.start_download(study_language(json_body().get("language")))
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())


@bp.post("/api/translate/models/<source>/<target>/delete")
def api_delete_translate_model(source: str, target: str):
    try:
        translation.delete_model(source, target)
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())
