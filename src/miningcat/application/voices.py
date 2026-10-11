"""The voices reading the cards' sentences and the books: OmniVoice's when it's installed (local, every language),
Edge's when the settings use edge-tts (faster, online), and the local voices of the languages Edge lacks (Taigi's
MMS). The first one is the default."""
from miningcat.application.anki.config import get_config
from miningcat.domain.languages import Language, Voice
from miningcat.infrastructure.speech import mms_tts, omnivoice_tts


def is_edge(voice_id: str) -> bool:
    return not (mms_tts.is_local(voice_id) or omnivoice_tts.is_voice(voice_id))


def language_voices(lang: Language) -> list[Voice]:
    """The voices of a language variant, the default one first: Edge's first when the settings use edge-tts, else the
    local ones (Taigi's MMS before OmniVoice, its own voice)."""
    edge = [v for v in lang.profile.voices if is_edge(v.voice_id)] if get_config()["tts_use_edge"] else []
    local = [v for v in lang.profile.voices if not is_edge(v.voice_id)]
    key = lang.profile.key
    if omnivoice_tts.installed() and omnivoice_tts.supports(key):
        local.append(Voice(omnivoice_tts.voice_label(key), omnivoice_tts.voice_id(key)))
    return edge + local


def voice_id(lang: Language, label: str) -> str | None:
    """The id of a voice of the language variant, by its label (the converter's dropdown)."""
    return next((v.voice_id for v in language_voices(lang) if v.label == label), None)
