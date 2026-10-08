import re

from miningcat.application.anki.config import get_config
from miningcat.domain.languages import Language, language_key
from miningcat.infrastructure.speech import mms_tts
from miningcat.infrastructure.speech.edge_tts import EdgeTts
from miningcat.infrastructure.speech.local_models import SpeechError

MAX_CHARS = 1000


class TtsError(Exception):
    pass


# "zh-TW-HsiaoChenNeural" -> "zh", "zh-HK-HiuMaanNeural" -> "yue" (Edge's Hong Kong voices speak Cantonese).
def _voice_language(voice_id: str) -> str:
    locale = "-".join(voice_id.split("-")[:2])
    return "yue" if locale.lower() == "zh-hk" else language_key(locale)


def voices(language: str) -> dict:
    """{voices: [{id, label}], default: id} for a language key ("zh", "ja"...)."""
    found, default = [], ""
    for lang in Language:
        for voice in lang.profile.voices:
            if _voice_language(voice.voice_id) != language:
                continue
            found.append({"id": voice.voice_id, "label": voice.label})
            if not default and voice == lang.profile.default_voice:
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


def synthesize(language: str, text: str, voice: str) -> bytes:
    """The text read by the voice, as MP3."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        raise TtsError("There's no sentence to read.")
    if len(text) > MAX_CHARS:
        raise TtsError(f"Sentences are limited to {MAX_CHARS} characters.")
    if voice not in {v["id"] for v in voices(language)["voices"]}:
        raise TtsError(f"Unknown voice: {voice!r}")
    if mms_tts.is_local(voice):
        try:
            return mms_tts.synthesize_mp3(text, voice)
        except SpeechError as exc:
            raise TtsError(str(exc))
        except Exception as exc:  # a model that couldn't be downloaded...
            raise TtsError(f"The voice couldn't be generated: {exc}")
    try:
        audio = tts.synthesize(text, voice)
    except ImportError:
        raise TtsError("Text-to-speech needs the edge-tts package (pip install edge-tts).")
    except Exception as exc:  # network errors, Edge refusing the request...
        raise TtsError(f"The voice couldn't be generated: {exc}")
    if not audio:
        raise TtsError("The voice couldn't be generated: Edge returned no audio.")
    return audio
