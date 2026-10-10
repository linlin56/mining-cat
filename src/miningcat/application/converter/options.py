"""What the converter offers for a language: the dropdowns of the GUIs, and the checks of their values."""
from miningcat.application.converter.modes import ConversionMode
from miningcat.application.mining import translation
from miningcat.config.app_info import GITHUB_URL
from miningcat.domain.languages import Language, SpeechEngine
from miningcat.domain.ocr.sampling import DEFAULT_REGION, OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN
from miningcat.domain.text.script_conversion import CONVERSION_TARGETS
from miningcat.infrastructure.downloads.registry import video_handlers
from miningcat.infrastructure.media.audio_files import AUDIO_EXTENSIONS
from miningcat.infrastructure.speech import engine_install, qwen3_asr

SOURCES = ["Audiobook / Ebook", "Video", "Video game / Screen share", "CSV to cards"]
PRECISION_VALUES = ["Tiny", "Base (default)", "Small", "Medium", "Large", "Turbo (fast, large-v3)"]
DEFAULT_PRECISION = "Base (default)"
# Precision of the languages transcribed by Qwen3-ASR instead of Whisper (Taigi).
QWEN3_PRECISION_VALUES = ["Qwen3-ASR 0.6B (default)", "Qwen3-ASR 1.7B (more accurate, slower)"]
# Offered after Whisper's for the other languages Qwen3-ASR knows, when it's installed (`make install-qwen`).
OPTIONAL_QWEN3_VALUES = ["Qwen3-ASR 0.6B", "Qwen3-ASR 1.7B (more accurate, slower)"]
INPUT_MODES = ["From web", "Local file"]
NO_CONVERSION = "No conversion"

VIDEO_EXTENSIONS = ("mp4", "mkv", "mov", "avi", "webm", "m4v")
EBOOK_EXTENSIONS = ("epub", "txt")

_CHANNEL_LABELS = {1: "mono", 2: "stereo"}


def convert_labels_for(lang: Language) -> list[str]:
    """The script conversions offered for a language: none, the other Chinese scripts, or Taigi's writing systems."""
    script = lang.profile.script
    return [NO_CONVERSION] + [label for label, _ in CONVERSION_TARGETS.get(script, [])]


def convert_target(label: str | None, lang: Language) -> str | None:
    """The script of a conversion label, None for no (or an unknown) conversion."""
    return dict(CONVERSION_TARGETS.get(lang.profile.script, [])).get(label)


def precision_values_for(lang: Language, aligning: bool = False) -> list[str]:
    """The speech models offered for a language: Whisper's, or Qwen3-ASR's. Some languages (like Cantonese) are only
    known to the large-v3 and turbo checkpoints: smaller models are hidden rather than left to fail. Qwen3-ASR's come
    after Whisper's when it's installed, except to align a book (`aligning`): it only transcribes."""
    if lang.profile.transcriber is SpeechEngine.QWEN3_ASR:
        return QWEN3_PRECISION_VALUES
    values = PRECISION_VALUES
    if lang.profile.large_whisper_models_only:
        values = [v for v in PRECISION_VALUES if v.split()[0] in ("Large", "Turbo")]
    if not aligning and qwen3_asr.supports(lang) and qwen3_asr.installed():
        values = values + OPTIONAL_QWEN3_VALUES
    return values


def model_from_precision(label: str) -> str:
    """"Base (default)" -> "base", "Qwen3-ASR 1.7B (...)" -> "qwen3-1.7b": the model name of the CLI."""
    words = label.split()
    if words[0] == "Qwen3-ASR":
        return f"qwen3-{words[1].lower()}"
    return words[0].lower()


def model_for(label: str | None, lang: Language, aligning: bool = False) -> str:
    """The speech model of a precision label, the default one (or the first offered) for an unknown label."""
    values = precision_values_for(lang, aligning)
    if label not in values:
        label = DEFAULT_PRECISION if DEFAULT_PRECISION in values else values[0]
    return model_from_precision(label)


def engines_to_install(lang: Language) -> str | None:
    """The local engines the language needs and that aren't installed (engine_install.QWEN or TAIGI), None when
    it has them or Whisper and Edge do its speech: the page offers to install them."""
    profile = lang.profile
    if profile.aligner is SpeechEngine.MMS:
        engines = engine_install.TAIGI
    elif profile.transcriber is SpeechEngine.QWEN3_ASR:
        engines = engine_install.QWEN
    else:
        return None
    return None if engine_install.installed(engines) else engines


def supports_character_list(lang: Language) -> bool:
    return lang.profile.character_list is not None


def language_options(lang: Language) -> dict:
    voices = lang.profile.voices
    return {
        "id": lang.id,
        "label": lang.profile.label,
        "convert": convert_labels_for(lang),
        "voices": [voice.label for voice in voices],
        "default_voice": voices[0].label if voices else "",
        "precision": precision_values_for(lang),
        "align_precision": precision_values_for(lang, aligning=True),
        "char_list": supports_character_list(lang),
        "needs_install": engines_to_install(lang),
        # its subtitles can be translated to the language of the settings (second subtitles)
        "translatable": translation.translatable(lang.profile.key) and lang.profile.key != translation.target_language(),
    }


def all_options(languages: list[Language]) -> dict:
    """Everything the converter page needs, for some language variants (those of the language studied)."""
    return {
        "languages": [language_options(lang) for lang in languages],
        "default_language": languages[0].id if languages else None,
        "sources": SOURCES,
        "modes": ConversionMode.labels(),
        "default_precision": DEFAULT_PRECISION,
        "audio_extensions": list(AUDIO_EXTENSIONS),
        "ebook_extensions": list(EBOOK_EXTENSIONS),
        "video_extensions": list(VIDEO_EXTENSIONS),
        "websites": video_handlers.websites,
        "input_modes": INPUT_MODES,
        "url_hints": video_handlers.url_hints,
        "ocr": {
            "fps_min": OCR_FPS_MIN,
            "fps_max": OCR_FPS_MAX,
            "fps_default": OCR_FPS_DEFAULT,
            "default_region": list(DEFAULT_REGION),
        },
        "github_url": GITHUB_URL,
        "translation_target": translation_target(),
    }


def translation_target() -> dict | None:
    """{"id", "name", "model"} of the language second subtitles are translated to and of the model translating them
    (the settings'), None when there's none."""
    target = translation.target_language()
    return {"id": target, "name": translation.LANGUAGES[target], "model": translation.model_label()} if target else None


def validate_video_url(url: str, website: str) -> str | None:
    """An error message when the URL isn't one of the selected website (or of any supported one), else None."""
    if not url:
        return None
    hint = video_handlers.url_hints.get(website, "")
    try:
        handler = video_handlers.for_url(url)
    except ValueError:
        return f"This doesn't look like a supported video URL.\nExpected {website} format: {hint}"
    expected = video_handlers.for_website(website)
    if expected is not None and handler is not expected:
        return f"This URL doesn't match the selected website ({website}).\nExpected format: {hint}"
    return None


def audio_track_label(track: dict) -> str:
    """"Track 1 - Mandarin (Taiwan) - stereo". The title tag tells apart variants sharing a language code
    (Mandarin and Cantonese are both "chi")."""
    name = track.get("title") or track.get("language") or "unknown language"
    parts = [f"Track {track['index']}", name]
    channels = _CHANNEL_LABELS.get(track.get("channels"))
    if channels:
        parts.append(channels)
    return " - ".join(parts)
