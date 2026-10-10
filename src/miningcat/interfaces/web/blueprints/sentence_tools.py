"""Tools of the card creator: readings of a sentence's words, word recordings, sentence audio and translation; and
Taigi's writing systems, for the Clipboard page."""
import base64

from flask import Blueprint, jsonify, request

from miningcat.application.mining import sentence_readings, sentence_tts, translation, word_audio
from miningcat.domain.text import taigi
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("sentence_tools", __name__)


@bp.post("/api/sentence/readings")
def api_sentence_readings():
    body = json_body()
    sentence = str(body.get("sentence") or "")[:5000]
    return jsonify(sentence_readings.annotate(study_language(body.get("language")), sentence, str(body.get("reading") or "")))


# A Taigi text written in Hanji, Tâi-lô or POJ (from any of them, or a mix): the Clipboard page's "Write in".
@bp.post("/api/taigi/convert")
def api_taigi_convert():
    body = json_body()
    text, target = str(body.get("text") or ""), str(body.get("target") or "")
    if len(text) > 200_000:
        raise UserError("Error", "The text is too long to convert (200,000 characters at most).")
    try:
        return jsonify(text=taigi.convert(text, target, numbers=bool(body.get("numbers"))))
    except (ValueError, RuntimeError) as exc:
        raise UserError("Error", str(exc))


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
    chosen = sentence_tts.default_voice(language)
    sentence_tts.preload(chosen)
    return jsonify(**sentence_tts.voices(language), chosen=chosen)


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
    """The languages sentences can be translated to, by the engine of the settings or the one asked for (?engine=)."""
    engine = request.args.get("engine") or translation.engine()
    if engine not in translation.ENGINES:
        raise UserError("Translation", f"Unknown translation engine: {engine!r}")
    return jsonify(languages=translation.targets(engine), chosen=translation.target_language(),
                   engines=translation.engines(), engine=translation.engine())


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


# NLLB-200's models (optional): installed in the background, like the downloads of Argos' models.
@bp.post("/api/translate/engines/<name>/install")
def api_install_translate_engine(name: str):
    try:
        translation.start_install(name)
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())


@bp.post("/api/translate/engines/<name>/delete")
def api_delete_translate_engine(name: str):
    try:
        translation.delete_engine(name)
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())
