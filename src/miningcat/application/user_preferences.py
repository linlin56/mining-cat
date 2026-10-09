"""The user's preferences for every page (Settings › User preferences), kept in user/user-config.json."""
from miningcat.config.paths import paths
from miningcat.infrastructure.files.json_files import read_json, write_json

# Each preference and its choices, the first one by default.
CHOICES = {
    "theme": ("system", "light", "dark"),           # the colour mode; "system": the OS's
    "highlights": ("default", "deutan", "tritan"),  # the highlight colours of the text, for colour blindness
    "discord": ("on", "off"),                       # the Discord status: what the user does in MiningCat
}


def get_preferences() -> dict:
    saved = read_json(paths.user_config, {})
    if not isinstance(saved, dict):
        saved = {}
    return {key: saved[key] if saved.get(key) in choices else choices[0] for key, choices in CHOICES.items()}


def save_preferences(values: dict) -> dict:
    """Keeps the known preferences of `values` with a valid choice; the others are left as they are."""
    preferences = get_preferences()
    for key, choices in CHOICES.items():
        if values.get(key) in choices:
            preferences[key] = values[key]
    write_json(paths.user_config, preferences)
    return preferences
