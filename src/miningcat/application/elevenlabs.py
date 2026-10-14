"""The settings of ElevenLabs, the online voice of the user's own account (infrastructure/speech/elevenlabs_tts.py):
the API key, the model, the voice of each study language, and whether it's the main voice.

Each character read uses the account's credits: until the user makes it the main voice, ElevenLabs is only offered
in the lists (last), never picked by default, so that no card nor book is read by it unless the user chose it.

The API key is kept encrypted (infrastructure/persistence/secrets.py)."""
from miningcat.application.anki.config import get_config, save_config
from miningcat.domain.cards.errors import AnkiError
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.persistence import secrets
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.speech import elevenlabs_tts
from miningcat.infrastructure.speech.elevenlabs_tts import ElevenLabs, ElevenLabsError

_SETTING = "elevenlabs"
LATEST = ""  # the model setting meaning "ElevenLabs' latest model that reads the language"
_latest: dict[tuple[str, str], str] = {}  # (key, language) -> the latest model, asked once per run


def get_settings() -> dict:
    """The settings, with the API key decrypted ("" and `key_error` when it can't be: its key file is missing)."""
    config = settings.get(_SETTING, {}) or {}
    config.setdefault("api_key", "")
    config.setdefault("model", LATEST)
    config.setdefault("voices", {})       # study language -> the id of its voice at ElevenLabs
    config.setdefault("voice_names", {})  # study language -> the voice's name, when the key may read it
    config.setdefault("main", False)      # ElevenLabs reads everything (it's the default voice)
    stored = config["api_key"]
    try:
        config["api_key"] = secrets.decrypt(stored)
    except secrets.SecretError as exc:
        config["api_key"], config["key_error"] = "", str(exc)
    if stored and not secrets.is_encrypted(stored):  # saved before keys were encrypted
        _save(config)
    return config


def _save(config: dict) -> None:
    stored = {key: value for key, value in config.items() if key != "key_error"}
    if config.get("key_error") and not config["api_key"]:  # unreadable for now: kept, its key file may come back
        stored["api_key"] = (settings.get(_SETTING, {}) or {}).get("api_key", "")
    else:
        stored["api_key"] = secrets.encrypt(config["api_key"])
    settings.set(_SETTING, stored)


def voice(language: str) -> str:
    """The id at ElevenLabs of the voice of a study language, "" when ElevenLabs doesn't read it (no key or voice)."""
    config = get_settings()
    return config["voices"].get(language, "") if config["api_key"] else ""


def is_main() -> bool:
    return get_settings()["main"]


def voice_label(language: str) -> str:
    name = get_settings()["voice_names"].get(language)
    return f"ElevenLabs - {name} (uses credits)" if name else "ElevenLabs (uses credits)"


def client() -> ElevenLabs:
    return ElevenLabs(get_settings()["api_key"])


def model(language: str) -> str:
    """The model reading the language: the one of the settings, else the latest one listing the language (the
    latest of all when none lists it)."""
    config = get_settings()
    if config["model"] != LATEST:
        return config["model"]
    key = (config["api_key"], language)
    if key not in _latest:
        models = client().models()
        if not models:
            raise ElevenLabsError("ElevenLabs lists no model that reads text.")
        _latest[key] = next((m["id"] for m in models if language in m["languages"]), models[0]["id"])
    return _latest[key]


def public_settings(language: str) -> dict:
    """What the settings page shows: never the key itself, only its end."""
    config = get_settings()
    key = config["api_key"]
    return {
        "has_key": bool(key), "key_hint": f"…{key[-4:]}" if key else "", "model": config["model"],
        "voice": config["voices"].get(language, ""), "voice_name": config["voice_names"].get(language, ""),
        "main": config["main"], "permissions": list(elevenlabs_tts.PERMISSIONS), "key_error": config.get("key_error", ""),
        "voice_library": elevenlabs_tts.VOICE_LIBRARY_URL,
    }


def save_settings(values: dict, language: str) -> dict:
    """Saves the key, the model, the voice of the language and the main option (each only when given). The voice's
    name is asked to ElevenLabs when the key may read it."""
    config = get_settings()
    if "api_key" in values:
        key = str(values["api_key"] or "").strip()
        if key and not key.startswith(elevenlabs_tts.KEY_PREFIX):
            raise ElevenLabsError(f"This isn't an ElevenLabs API key: they start with {elevenlabs_tts.KEY_PREFIX!r} and are "
                                  "only shown once, when the key is created (the list of keys shows their ID).")
        config["api_key"] = key
    if "model" in values:
        config["model"] = str(values["model"] or LATEST).strip()
    if "voice" in values:
        if language not in LANGUAGES:
            raise AnkiError(f"Unknown language: {language!r}")
        voice_id = str(values["voice"] or "").strip()
        config["voices"][language] = voice_id
        config["voice_names"].pop(language, None)
        if voice_id and config["api_key"]:
            try:
                config["voice_names"][language] = ElevenLabs(config["api_key"]).voice_name(voice_id)
            except ElevenLabsError:
                pass  # no Voices: read permission (or offline): the voice keeps no name
    if "main" in values:
        config["main"] = bool(values["main"])
    _save(config)
    _sentence_voices(config)
    return public_settings(language)


# The voice reading the cards' sentences (Settings › Anki) follows the main option: ElevenLabs when it becomes the
# main voice, the language's default again when it stops being so. "None" (sentences read by hand) is kept.
def _sentence_voices(config: dict) -> None:
    chosen = get_config()["tts_voices"]
    changes = {}
    for language, voice_id in config["voices"].items():
        ours = elevenlabs_tts.voice_id(language)
        main = config["main"] and voice_id and config["api_key"]
        if main and chosen.get(language) != "":
            changes[language] = ours
        elif not main and chosen.get(language) == ours:
            changes[language] = None
    if changes:
        save_config({"tts_voices": changes})


def models() -> list[dict]:
    return client().models()


def credits() -> dict:
    return client().credits()
