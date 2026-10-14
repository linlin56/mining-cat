"""The voices reading the cards' sentences and the books: OmniVoice's when it's installed (local, every language),
Edge's when the settings use edge-tts (faster, online), the local voices of the languages Edge lacks (Taigi's MMS),
and ElevenLabs' when the user set it up with their own account (online, paid). The first one is the default:
ElevenLabs is only first when it's the main voice (application/elevenlabs.py)."""
from miningcat.application import elevenlabs
from miningcat.application.anki.config import get_config
from miningcat.domain.languages import Language, Voice
from miningcat.infrastructure.speech import elevenlabs_tts, mms_tts, omnivoice_tts


def is_edge(voice_id: str) -> bool:
    return not (mms_tts.is_local(voice_id) or omnivoice_tts.is_voice(voice_id) or elevenlabs_tts.is_voice(voice_id))


def language_voices(lang: Language) -> list[Voice]:
    """The voices of a language variant, the default one first: ElevenLabs' when it's the main voice, then Edge's
    when the settings use edge-tts, then the local ones (Taigi's MMS before OmniVoice, its own voice), then
    ElevenLabs' when it isn't the main voice."""
    edge = [v for v in lang.profile.voices if is_edge(v.voice_id)] if get_config()["tts_use_edge"] else []
    local = [v for v in lang.profile.voices if not is_edge(v.voice_id)]
    key = lang.profile.key
    if omnivoice_tts.installed() and omnivoice_tts.supports(key):
        local.append(Voice(omnivoice_tts.voice_label(key), omnivoice_tts.voice_id(key)))
    if not elevenlabs.voice(key):
        return edge + local
    online = [Voice(elevenlabs.voice_label(key), elevenlabs_tts.voice_id(key))]
    return online + edge + local if elevenlabs.is_main() else edge + local + online


def may_default(voice_id: str) -> bool:
    """Whether a voice may be picked without the user asking for it: not ElevenLabs', unless it's the main voice
    (it uses credits)."""
    return not elevenlabs_tts.is_voice(voice_id) or elevenlabs.is_main()


def default_voice(lang: Language) -> Voice | None:
    """The voice a language variant is read by when the user didn't pick one."""
    return next((v for v in language_voices(lang) if may_default(v.voice_id)), None)


def voice_id(lang: Language, label: str) -> str | None:
    """The id of a voice of the language variant, by its label (the converter's dropdown)."""
    return next((v.voice_id for v in language_voices(lang) if v.label == label), None)
