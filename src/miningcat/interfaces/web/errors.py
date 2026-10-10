"""Errors shown to the user in a dialog: {"title", "error"} with an HTTP status."""
from flask import Flask, jsonify

from miningcat.application.converter.errors import ConverterError
from miningcat.application.mining.sentence_tts import TtsError
from miningcat.domain.cards.errors import AnkiError, AnkiUnavailable
from miningcat.domain.dictionary.errors import DictionaryError
from miningcat.domain.library.errors import AudioError, BookError, ComicError, VideoError
from miningcat.domain.words.status import WordError
from miningcat.infrastructure.capture import CaptureError
from miningcat.infrastructure.translation.errors import TranslateError


class UserError(Exception):
    """An error meant to be shown to the user in a dialog."""

    def __init__(self, title: str, message: str, status: int = 400):
        super().__init__(message)
        self.title = title
        self.message = message
        self.status = status


# The dialog title of the errors of each part of the app.
TITLES: dict[type[Exception], str] = {
    BookError: "Reader",
    AudioError: "Audio",
    ComicError: "Comics",
    VideoError: "Player",
    DictionaryError: "Dictionary",
    WordError: "Words",
    AnkiError: "Anki",
    CaptureError: "Screen capture",
    TranslateError: "Translation",
    TtsError: "Text-to-speech",
}


def register(app: Flask) -> None:
    @app.errorhandler(UserError)
    def _user_error(exc: UserError):
        return jsonify(title=exc.title, error=exc.message), exc.status

    @app.errorhandler(ConverterError)
    def _converter_error(exc: ConverterError):
        return jsonify(title=exc.title, error=str(exc)), 400

    @app.errorhandler(AnkiUnavailable)
    def _anki_unavailable(exc: AnkiUnavailable):
        return jsonify(title="Anki isn't reachable", error=str(exc), unavailable=True), 503

    for error, title in TITLES.items():
        app.register_error_handler(error, lambda exc, title=title: (jsonify(title=title, error=str(exc)), 400))
