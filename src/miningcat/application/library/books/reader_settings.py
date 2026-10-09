"""The reader's settings (font, theme, popup...), the same for every book."""
from miningcat.config.paths import paths
from miningcat.infrastructure.files.json_files import read_json, write_json

DEFAULT_SETTINGS = {
    "font_size": 20, "line_height": 1.8, "font": "serif", "theme": "light",
    "margin": 48, "furigana": True,
    # MiningCat's dictionary popup: "click" a word, "shift" + hover like Yomitan, or "off" to use Yomitan.
    "lookup": "click",
    # Words coloured by their status ("status"), or not at all ("off").
    "colors": "status",
    # Recommended (i+1) sentences underlined in the text.
    "i1": True,
}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **read_json(paths.reader_settings, {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif isinstance(default, (int, float)):
            try:
                value = type(default)(value)
            except (TypeError, ValueError):
                continue
            limits = {"font_size": (10, 48), "line_height": (1.1, 3.0), "margin": (0, 160)}[key]
            settings[key] = max(limits[0], min(limits[1], value))
        elif key == "font" and value in ("serif", "sans"):
            settings[key] = value
        elif key == "theme" and value in ("light", "sepia", "dark", "auto"):
            settings[key] = value
        elif key == "lookup" and value in ("click", "shift", "off"):
            settings[key] = value
        elif key == "colors" and value in ("status", "off"):
            settings[key] = value
    write_json(paths.reader_settings, settings)
    return settings
