import re

from miningcat.domain.cards.errors import AnkiError
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.words.status import DEFAULT_KNOWN_INTERVAL
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.translation.install import DEFAULT_MODEL as DEFAULT_TRANSLATION_MODEL
from miningcat.infrastructure.translation.install import MODELS as TRANSLATION_MODELS

DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_TAG = "mining-cat"
OLD_DEFAULT_TAG = "miningcat"
_SETTING = "anki"


def get_config() -> dict:
    """The settings of the cards (they also hold the voice reading the sentences, and the translation language)."""
    config = settings.get(_SETTING, {}) or {}
    config.setdefault("url", DEFAULT_URL)
    config.setdefault("known_interval", DEFAULT_KNOWN_INTERVAL)
    config.setdefault("notes", {})   # language -> {deck, model, fields: {note field: template}, tags}
    config.setdefault("sync", {})    # language -> [{deck, field, reading_field}]
    config.setdefault("tts_voices", {})  # language -> Edge-TTS voice reading the sentences, "" = none
    config.setdefault("translation_language", "en")  # sentences are translated to it, "" = not translated
    config.setdefault("translation_model", DEFAULT_TRANSLATION_MODEL)  # the model translating them (install.MODELS)
    # Qwen3 also translates the cards' sentences, when it's the model (else NLLB-200 does)
    config.setdefault("translation_cards_with_context", False)
    config.pop("translation_engine", None)  # Argos Translate or NLLB-200, before Argos was removed
    for setup in config["notes"].values():
        if setup.get("tags") == OLD_DEFAULT_TAG:  # the default tag was "miningcat" before
            setup["tags"] = DEFAULT_TAG
    return config


def save_config(values: dict) -> dict:
    config = get_config()
    if "url" in values:
        url = str(values["url"] or DEFAULT_URL).strip()
        if not re.match(r"^https?://", url):
            raise AnkiError("The AnkiConnect address must start with http:// or https://")
        config["url"] = url.rstrip("/")
    if "known_interval" in values:
        try:
            config["known_interval"] = max(1, min(3650, int(values["known_interval"])))
        except (TypeError, ValueError):
            raise AnkiError("Invalid interval.")
    for language, setup in (values.get("notes") or {}).items():
        if language not in LANGUAGES:
            continue
        if setup is None:
            config["notes"].pop(language, None)
            continue
        config["notes"][language] = {
            "deck": str(setup.get("deck") or ""),
            "model": str(setup.get("model") or ""),
            "fields": {str(k): str(v) for k, v in (setup.get("fields") or {}).items()},
            "tags": str(setup.get("tags") or DEFAULT_TAG),
        }
    if "translation_language" in values:
        target = str(values["translation_language"] or "")
        if target and target not in LANGUAGES:
            raise AnkiError(f"Unknown language: {target!r}")
        config["translation_language"] = target
    if "translation_model" in values:
        name = str(values["translation_model"] or DEFAULT_TRANSLATION_MODEL)
        if name not in TRANSLATION_MODELS:
            raise AnkiError(f"Unknown translation model: {name!r}")
        config["translation_model"] = name
    if "translation_cards_with_context" in values:
        config["translation_cards_with_context"] = bool(values["translation_cards_with_context"])
    for language, voice in (values.get("tts_voices") or {}).items():
        if language in LANGUAGES:
            config["tts_voices"][language] = str(voice or "")
    for language, sources in (values.get("sync") or {}).items():
        if language not in LANGUAGES:
            continue
        config["sync"][language] = [
            {"deck": str(s.get("deck") or ""), "field": str(s.get("field") or ""), "reading_field": str(s.get("reading_field") or "")}
            for s in (sources or []) if s.get("deck") and s.get("field")
        ]
    settings.set(_SETTING, config)
    return config


def note_setup(language: str) -> dict:
    """The deck, note type and field templates of the cards of a language."""
    setup = get_config()["notes"].get(language)
    if not setup or not setup.get("deck") or not setup.get("model") or not setup.get("fields"):
        raise AnkiError(f"Choose the Anki deck and note type for {LANGUAGES.get(language, language)} in Settings › Anki first.")
    return setup



def anki() -> AnkiConnect:
    """The AnkiConnect client at the address of the settings."""
    return AnkiConnect(get_config()["url"])
