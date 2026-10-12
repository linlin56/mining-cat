import re
from dataclasses import dataclass

from miningcat.application.anki.config import get_config
from miningcat.application.voices import language_voices
from miningcat.domain.languages import Language, language_key
from miningcat.infrastructure.speech import engine_install, mms_tts, omnivoice_tts
from miningcat.infrastructure.speech.edge_tts import EdgeTts
from miningcat.infrastructure.speech.local_models import SpeechError

MAX_CHARS = 1000


class TtsError(Exception):
    pass


# "zh-TW-HsiaoChenNeural" -> "zh", "zh-HK-HiuMaanNeural" -> "yue" (Edge's Hong Kong voices speak Cantonese),
# "yue-OmniVoice" -> "yue".
def _voice_language(voice_id: str) -> str:
    if omnivoice_tts.is_voice(voice_id):
        return omnivoice_tts.voice_language(voice_id)
    locale = "-".join(voice_id.split("-")[:2])
    return "yue" if locale.lower() == "zh-hk" else language_key(locale)


def voices(language: str) -> dict:
    """{voices: [{id, label}], default: id} for a language key ("zh", "ja"...): OmniVoice's when it's installed,
    Edge's when the settings use edge-tts (see application/voices.py)."""
    found, default = [], ""
    for lang in Language:
        variant_voices = language_voices(lang)
        for voice in variant_voices:
            if _voice_language(voice.voice_id) != language or voice.voice_id in {v["id"] for v in found}:
                continue
            found.append({"id": voice.voice_id, "label": voice.label})
            if not default and voice == variant_voices[0]:
                default = voice.voice_id
    return {"voices": found, "default": default or (found[0]["id"] if found else "")}


def default_voice(language: str) -> str:
    """The voice chosen in the settings for a language ("" when sentences aren't read), else the language's default."""
    available = voices(language)
    chosen = get_config()["tts_voices"].get(language)
    if chosen == "" or chosen in {v["id"] for v in available["voices"]}:
        return chosen
    return available["default"]


tts = EdgeTts()


def preload(voice: str) -> None:
    """A local voice loads in the background while the card is being made."""
    mms_tts.preload(voice)
    if omnivoice_tts.is_voice(voice):
        omnivoice_tts.preload()


@dataclass
class Speech:
    audio: bytes  # MP3
    notice: str = ""  # why another voice than the one asked for read it, for the user


def synthesize(language: str, text: str, voice: str) -> Speech:
    """The text read by the voice: OmniVoice's, MMS's or Edge's (OmniVoice taking over when Edge fails, with a notice)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        raise TtsError("There's no sentence to read.")
    if len(text) > MAX_CHARS:
        raise TtsError(f"Sentences are limited to {MAX_CHARS} characters.")
    if voice not in {v["id"] for v in voices(language)["voices"]}:
        raise TtsError(f"Unknown voice: {voice!r}")
    if mms_tts.is_local(voice):
        try:
            return Speech(mms_tts.synthesize_mp3(text, voice))
        except SpeechError as exc:
            raise TtsError(str(exc))
        except Exception as exc:  # a model that couldn't be downloaded...
            raise TtsError(f"The voice couldn't be generated: {exc}")
    if omnivoice_tts.is_voice(voice):
        return Speech(_omnivoice(language, text))
    try:
        return Speech(_edge(text, voice))
    except TtsError as edge_error:
        if not (omnivoice_tts.installed() and omnivoice_tts.supports(language)):
            raise
        try:  # Edge is down or offline: the local voice takes over
            audio = _omnivoice(language, text)
        except TtsError as exc:
            raise TtsError(f"{edge_error} The local voice couldn't take over: {exc}")
        return Speech(audio, "edge-tts isn't working right now: OmniVoice, the local voice, read it instead.")


def _omnivoice(language: str, text: str) -> bytes:
    try:
        return omnivoice_tts.synthesize_mp3(text, language, get_config()["tts_steps"])
    except SpeechError as exc:
        raise TtsError(str(exc))
    except Exception as exc:  # a model that couldn't be downloaded...
        raise TtsError(f"The voice couldn't be generated: {exc}")


def local_voice(language: str = "") -> dict:
    """OmniVoice's state, for the settings: installed or how to install it, the steps offered and chosen, and whether
    Edge's voices are used instead when available. For Taigi, its own local voice (MMS) as well: installed or not."""
    config = get_config()
    state = {
        "installed": omnivoice_tts.installed(), "install_command": omnivoice_tts.INSTALL_COMMAND,
        "steps": list(omnivoice_tts.STEPS), "chosen_steps": config["tts_steps"], "use_edge": config["tts_use_edge"],
    }
    if language == "nan":
        state["mms"] = {"installed": engine_install.installed(engine_install.TAIGI),
                        "install_command": "make install-taigi"}
    return state


def new_voice(language: str) -> None:
    """OmniVoice makes up another voice for the language, used from its next sentence."""
    try:
        omnivoice_tts.new_voice(language)
    except SpeechError as exc:
        raise TtsError(str(exc))


def _edge(text: str, voice: str) -> bytes:
    try:
        audio = tts.synthesize(text, voice)
    except ImportError:
        raise TtsError("Text-to-speech needs the edge-tts package (pip install edge-tts).")
    except Exception as exc:  # network errors, Edge refusing the request...
        raise TtsError(f"The voice couldn't be generated: {exc}")
    if not audio:
        raise TtsError("The voice couldn't be generated: Edge returned no audio.")
    return audio
