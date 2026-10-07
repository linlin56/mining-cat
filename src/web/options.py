from language import Language
from gui_components.constants import (
    _CONVERT_OPTIONS_FOR_SCRIPT,
    DEFAULT_VOICE_FOR_LANGUAGE,
    INPUT_MODES,
    LARGE_ONLY_WHISPER_CODES,
    TARGET_WEBSITES,
    URL_HINT_BY_WEBSITE,
    VOICES_FOR_LANGUAGE,
)

MODES = ["Standard", "Generate subtitles", "Generate audio"]
SOURCES = ["Audiobook / Ebook", "Video", "Video game / Screen share", "CSV to cards"]
PRECISION_VALUES = ["Tiny", "Base (default)", "Small", "Medium", "Large", "Turbo (fast, large-v3)"]
DEFAULT_PRECISION = "Base (default)"

VIDEO_EXTENSIONS = ("mp4", "mkv", "mov", "avi", "webm", "m4v")
EBOOK_EXTENSIONS = ("epub", "txt")

_CHANNEL_LABELS = {1: "mono", 2: "stereo"}

# Chinese script per language, duplicated from chinese_converter.SCRIPT_FOR_LANGUAGE
# so that building the dropdowns doesn't require importing opencc.
_SCRIPT_FOR_LANGUAGE = {
    Language.MANDARIN_CN: "s",
    Language.MANDARIN_TW: "tw",
    Language.CANTONESE_HK: "hk",
}


def convert_labels_for(lang: Language) -> list[str]:
    script = _SCRIPT_FOR_LANGUAGE.get(lang)
    if script is None:
        return ["No conversion"]
    return [label for label, _ in _CONVERT_OPTIONS_FOR_SCRIPT[script]]


# Some languages (like Cantonese) are only known to Whisper's large-v3/turbo checkpoints:
# smaller models are hidden rather than left in the list to fail during transcription.
def precision_values_for(lang: Language) -> list[str]:
    if lang.value.whisper_code not in LARGE_ONLY_WHISPER_CODES:
        return PRECISION_VALUES
    return [v for v in PRECISION_VALUES if v.split()[0] in ("Large", "Turbo")]


# "Base (default)" -> "base", the model name expected by the CLI.
def model_from_precision(label: str) -> str:
    return label.split()[0].lower()


def supports_character_list(lang: Language) -> bool:
    from frequency import character_frequency
    return character_frequency.supports_language(lang)


def language_options(lang: Language) -> dict:
    voices = VOICES_FOR_LANGUAGE.get(lang, [])
    return {
        "id": lang.name.lower(),
        "label": lang.value.label,
        "convert": convert_labels_for(lang),
        "voices": [label for label, _ in voices],
        "default_voice": DEFAULT_VOICE_FOR_LANGUAGE.get(lang, voices[0][0] if voices else ""),
        "precision": precision_values_for(lang),
        "char_list": supports_character_list(lang),
    }


# Only the variants of the language studied (see web/profile.py): Mandarin is Taiwan or China, French is French.
def all_options(study_language: str | None = None) -> dict:
    from config import AUDIO_EXTENSIONS
    from web.profile import converter_languages
    from ocr_mining.frames import DEFAULT_REGION, OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN
    from gui_components.constants import GITHUB_URL

    languages = converter_languages(study_language) if study_language else list(Language)
    return {
        "languages": [language_options(lang) for lang in languages],
        "default_language": languages[0].name.lower() if languages else None,
        "sources": SOURCES,
        "modes": MODES,
        "default_precision": DEFAULT_PRECISION,
        "audio_extensions": list(AUDIO_EXTENSIONS),
        "ebook_extensions": list(EBOOK_EXTENSIONS),
        "video_extensions": list(VIDEO_EXTENSIONS),
        "websites": TARGET_WEBSITES,
        "input_modes": INPUT_MODES,
        "url_hints": URL_HINT_BY_WEBSITE,
        "ocr": {
            "fps_min": OCR_FPS_MIN,
            "fps_max": OCR_FPS_MAX,
            "fps_default": OCR_FPS_DEFAULT,
            "default_region": list(DEFAULT_REGION),
        },
        "github_url": GITHUB_URL,
    }


# Checks the entered URL against the selected website.
# Returns an error message if they don't match (wrong site picked, or an unsupported platform altogether), else None.
def validate_video_url(url: str, website: str) -> str | None:
    if not url:
        return None
    import video_handlers

    hint = URL_HINT_BY_WEBSITE.get(website, "")
    try:
        handler = video_handlers.get_handler(url)
    except ValueError:
        return f"This doesn't look like a supported video URL.\nExpected {website} format: {hint}"

    handler_by_website = {
        "Instagram": video_handlers.instagram,
        "YouTube": video_handlers.youtube,
        "Bilibili": video_handlers.bilibili,
    }
    expected = handler_by_website.get(website)
    if expected is not None and handler is not expected:
        return f"This URL doesn't match the selected website ({website}).\nExpected format: {hint}"
    return None


# Prefer the "title" tag (e.g. "Mandarin (Taiwan)") if available:
# the "language" tag alone can't tell apart variants sharing one ISO 639-2 code (Mandarin/Cantonese are all "chi").
def audio_track_label(track: dict) -> str:
    name = track.get("title") or track.get("language") or "unknown language"
    parts = [f"Track {track['index']}", name]
    channels = _CHANNEL_LABELS.get(track.get("channels"))
    if channels:
        parts.append(channels)
    return " - ".join(parts)
