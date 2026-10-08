"""The audio of a converted book in the reader: a sentence played, or cut for the card creator."""
import base64

from flask import Blueprint, jsonify, send_file

from miningcat.application.library import book_audio, books
from miningcat.domain.languages import language_key
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("book_audio", __name__, url_prefix="/reader")

def _book_language(book_id: str) -> str:
    return language_key(books.get_prefs(book_id).get("language") or books.get_meta(book_id).get("language"))


def _chapter(value) -> int | None:
    return value if isinstance(value, int) else None


@bp.get("/api/books/<book_id>/audio")
def api_audio_info(book_id: str):
    return jsonify(audio=book_audio.info(book_id))


@bp.post("/api/books/<book_id>/audio/link")
def api_audio_link(book_id: str):
    return jsonify(audio=book_audio.attach_from_output(book_id))


@bp.post("/api/books/<book_id>/audio/delete")
def api_audio_delete(book_id: str):
    book_audio.remove(book_id)
    return jsonify(audio=None)


@bp.get("/api/books/<book_id>/audio/<int:track>")
def api_audio_track(book_id: str, track: int):
    return send_file(book_audio.track_path(book_id, track), conditional=True, max_age=3600)


# Where a sentence is in the audio: {"track", "start", "end", "url"}, or {"found": false}.
@bp.post("/api/books/<book_id>/audio/find")
def api_audio_find(book_id: str):
    body = json_body()
    span = book_audio.find_sentence(book_id, str(body.get("sentence") or ""), _chapter(body.get("chapter")),
                                    _book_language(book_id))
    if span is None:
        return jsonify(found=False)
    return jsonify(found=True, url=f"/reader/api/books/{book_id}/audio/{span['track']}", **span)


# The sentence's audio cut as MP3, as a data URL for the card creator's "Sentence audio".
@bp.post("/api/books/<book_id>/audio/clip")
def api_audio_clip(book_id: str):
    body = json_body()
    span = book_audio.find_sentence(book_id, str(body.get("sentence") or ""), _chapter(body.get("chapter")),
                                    _book_language(book_id))
    if span is None:
        return jsonify(found=False)
    data = book_audio.clip(book_id, span["track"], span["start"], span["end"])
    return jsonify(found=True, data="data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii"),
                   name="sentence.mp3", **span)
