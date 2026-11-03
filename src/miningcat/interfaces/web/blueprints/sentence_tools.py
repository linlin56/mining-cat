"""Tools of the card creator: readings of a sentence's words, word recordings, sentence audio and translation; and
the scripts of Chinese and Taigi, for the Clipboard page."""
import base64

from flask import Blueprint, jsonify, request

from miningcat.application import elevenlabs
from miningcat.application.mining import sentence_readings, sentence_tts, translation, word_audio
from miningcat.domain.text import taigi
from miningcat.domain.languages import TWO_SCRIPT_LANGUAGES
from miningcat.domain.text.chinese_script import chinese_main_script
from miningcat.domain.text.script_conversion import ConversionError, convert_chinese, sample
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


# A Chinese text as the Clipboard page shows it to read: in traditional or simplified characters, or as it is ("none").
# With the script of most of its characters, as read and as typed, for their language tags: told from a sample of it,
# a text of any length is read without delay.
@bp.post("/api/chinese/convert")
def api_chinese_convert():
    body = json_body()
    text, target = str(body.get("text") or ""), str(body.get("target") or "none")
    language = study_language(body.get("language"))
    if language not in TWO_SCRIPT_LANGUAGES:
        raise UserError("Error", f"{language!r} isn't written in traditional and simplified characters.")
    converted = text
    if target != "none":
        if len(text) > 200_000:
            raise UserError("Error", "The text is too long to convert (200,000 characters at most).")
        try:
            converted = convert_chinese(text, language, target)
        except ConversionError as exc:
            raise UserError("Error", str(exc))
    source = chinese_main_script(sample(text))
    return jsonify(text=converted, script=source if converted == text else chinese_main_script(sample(converted)),
                   source=source)


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


# OmniVoice, the local voice: installed or not, its steps. Its settings are saved with the cards' (/api/anki/config).
@bp.get("/api/tts/local-voice")
def api_tts_local_voice():
    language = request.args.get("language")
    return jsonify(sentence_tts.local_voice(study_language(language) if language else ""))


# OmniVoice makes up another voice for the language: its next sentence is read by it.
@bp.post("/api/tts/new-voice")
def api_tts_new_voice():
    try:
        sentence_tts.new_voice(study_language(json_body().get("language")))
    except sentence_tts.TtsError as exc:
        raise UserError("Text-to-speech", str(exc))
    return jsonify(ok=True)


# ElevenLabs, the online voice of the user's account: its settings for the language studied (never the key itself),
# its models and the credits left (asked to ElevenLabs with the key).
@bp.get("/api/tts/elevenlabs")
def api_tts_elevenlabs():
    return jsonify(elevenlabs.public_settings(study_language(request.args.get("language"))))


@bp.post("/api/tts/elevenlabs")
def api_tts_elevenlabs_save():
    body = json_body()
    values = {key: body[key] for key in ("api_key", "model", "voice", "main") if key in body}
    try:
        return jsonify(elevenlabs.save_settings(values, study_language(body.get("language"))))
    except elevenlabs.ElevenLabsError as exc:
        raise UserError("ElevenLabs", str(exc))


@bp.get("/api/tts/elevenlabs/account")
def api_tts_elevenlabs_account():
    try:
        return jsonify(models=elevenlabs.models(), credits=elevenlabs.credits())
    except elevenlabs.ElevenLabsError as exc:
        raise UserError("ElevenLabs", str(exc))


@bp.post("/api/tts")
def api_tts():
    body = json_body()
    try:
        speech = sentence_tts.synthesize(study_language(body.get("language")), str(body.get("text") or ""), str(body.get("voice") or ""))
    except sentence_tts.TtsError as exc:
        raise UserError("Text-to-speech", str(exc))
    return jsonify(data="data:audio/mpeg;base64," + base64.b64encode(speech.audio).decode("ascii"), name="sentence.mp3",
                   notice=speech.notice)


@bp.get("/api/translate/languages")
def api_translate_languages():
    return jsonify(languages=translation.targets(), chosen=translation.target_language(), model=translation.model_label())


@bp.post("/api/translate")
def api_translate():
    body = json_body()
    try:
        translated = translation.translate(study_language(body.get("language")), str(body.get("text") or ""))
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation=translated, target=translation.target_language())


# The NLLB-200 models: downloaded in the background (with the packages, when they're missing), removed.
@bp.get("/api/translate/models")
def api_translate_models():
    return jsonify(translation.models())


@bp.post("/api/translate/models/<name>/install")
def api_install_translate_model(name: str):
    try:
        translation.start_install(name)
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())


@bp.post("/api/translate/models/<name>/delete")
def api_delete_translate_model(name: str):
    try:
        translation.delete_model(name)
    except translation.TranslateError as exc:
        raise UserError("Translation", str(exc))
    return jsonify(translation.models())
