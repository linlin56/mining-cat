"""The comic reader's settings, the same for every comic."""
from miningcat.config.paths import paths
from miningcat.infrastructure.files.json_files import read_json, write_json

DEFAULT_SETTINGS = {
    "spread": "auto",     # "single", "double", or "auto" (two pages side by side when the window is wide)
    "first_single": True, # in two-page spreads, the cover stands alone (so that the spreads match the printed book)
    "text": "hover",      # OCR text over the page: "hover" (shown under the cursor), "always", or "boxes" (outlined)
    "colors": "status",   # words coloured by status when the text is shown, or "off"
}

_CHOICES = {"spread": ("auto", "single", "double"), "text": ("hover", "always", "boxes"), "colors": ("status", "off")}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **read_json(paths.comic_settings, {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        if isinstance(default, bool):
            settings[key] = bool(values[key])
        elif values[key] in _CHOICES[key]:
            settings[key] = values[key]
    write_json(paths.comic_settings, settings)
    return settings
