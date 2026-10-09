"""The player's settings, the same for every video."""
from miningcat.config.paths import paths
from miningcat.infrastructure.files.json_files import read_json, write_json

DEFAULT_SETTINGS = {
    "sub_size": 34,            # px, subtitles over the video
    "sub_display": "shown",    # "shown", "blur" (until hovered) or "hidden"
    "auto_pause": False,       # pause at the end of every subtitle
    "colors": "status",        # words coloured by status, or "off"
    "list": True,              # subtitle list next to the video
    "audio_before": 200,       # ms of audio kept before and after a line, on cards
    "audio_after": 200,
    "secondary_translation": True,  # the second subtitles' lines are the card's sentence translation
    "fullwidth_punctuation": True,  # ASCII punctuation in Chinese or Japanese subtitles replaced: , → ，
}

AUDIO_MARGIN_MAX_MS = 3000

_CHOICES = {"sub_display": ("shown", "blur", "hidden"), "colors": ("status", "off")}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **read_json(paths.player_settings, {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif key in ("sub_size", "audio_before", "audio_after"):
            low, high = (14, 80) if key == "sub_size" else (0, AUDIO_MARGIN_MAX_MS)
            try:
                settings[key] = max(low, min(high, int(value)))
            except (TypeError, ValueError):
                continue
        elif value in _CHOICES[key]:
            settings[key] = value
    write_json(paths.player_settings, settings)
    return settings
