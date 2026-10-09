"""Reading the requests of the page."""
from flask import request

from miningcat.domain.languages import LANGUAGES, Language, language_key
from miningcat.interfaces.web.errors import UserError


def json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def converter_language(value) -> Language:
    """A language variant of the converter, by id (mandarin_tw...)."""
    try:
        return Language.from_id(str(value))
    except ValueError:
        raise UserError("Unknown language", f"Unknown language: {value!r}")


def study_language(value) -> str:
    """A study language, by key or tag (zh, zh-Hant...)."""
    language = language_key(str(value or ""))
    if language not in LANGUAGES:
        raise UserError("Error", f"Unknown language: {value!r}")
    return language
