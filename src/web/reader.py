# reader.py - Flask blueprint of the ebook reader: library, chapters, images, progress and settings.
# The page itself (templates/reader.html + static/reader.js) does the layout and the pagination.

from flask import Blueprint, jsonify, render_template, request, send_file

from web import book_audio, books, profile

bp = Blueprint("reader", __name__, url_prefix="/reader")


@bp.errorhandler(books.BookError)
def _book_error(exc: books.BookError):
    return jsonify(title="Reader", error=str(exc)), 400


@bp.errorhandler(book_audio.AudioError)
def _audio_error(exc: book_audio.AudioError):
    return jsonify(title="Audio", error=str(exc)), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.get("/")
@bp.get("/<book_id>")
def page(book_id: str | None = None):
    return render_template("reader.html")


def _language_of(book_id: str, declared: str | None) -> str:
    from mining.languages import language_key
    return language_key(books.get_prefs(book_id).get("language") or declared)


# Only the books of the language studied (and those of no known language) are in the library.
@bp.get("/api/books")
def api_books():
    study = profile.current()
    shown = [b for b in books.list_books() if not study or _language_of(b["id"], b["language"]) in (study, "")]
    return jsonify(books=shown, extensions=list(books.BOOK_EXTENSIONS))


@bp.post("/api/books")
def api_import():
    from mining.languages import LANGUAGES

    study = profile.current()
    added, errors, elsewhere = [], [], []
    for upload in request.files.getlist("files"):
        name = upload.filename or "book"
        try:
            meta = books.import_book(name, upload.read())
            language = _language_of(meta["id"], meta["language"])
            # Detection can't tell Cantonese from Mandarin: a Chinese book belongs to the Chinese language studied.
            if study and language != study and (not language or profile.same_family(language, study)):
                books.save_prefs(meta["id"], {"language": profile.default_tag(study)})
            elif study and language != study:
                elsewhere.append(f"{meta['title']} ({LANGUAGES.get(language, language)})")
            added.append({"id": meta["id"], "title": meta["title"]})
        except books.BookError as exc:
            errors.append(f"{name}: {exc}")
        except Exception as exc:  # a broken file must not break the whole upload
            errors.append(f"{name}: could not be read ({exc})")
    return jsonify(added=added, errors=errors, elsewhere=elsewhere)


@bp.get("/api/books/<book_id>")
def api_book(book_id: str):
    meta = books.get_meta(book_id)
    return jsonify(book=meta, progress=books.get_progress(book_id), prefs=books.get_prefs(book_id))


@bp.get("/api/books/<book_id>/chapters/<int:index>")
def api_chapter(book_id: str, index: int):
    return jsonify(html=books.chapter_html(book_id, index))


@bp.get("/api/books/<book_id>/res/<path:ref>")
def api_resource(book_id: str, ref: str):
    return send_file(books.resource_path(book_id, ref), max_age=86400)


@bp.post("/api/books/<book_id>/progress")
def api_progress(book_id: str):
    body = _body()
    return jsonify(books.save_progress(book_id, body.get("chapter"), body.get("offset"), body.get("percent")))


@bp.post("/api/books/<book_id>/prefs")
def api_prefs(book_id: str):
    return jsonify(books.save_prefs(book_id, _body()))


@bp.post("/api/books/<book_id>/delete")
def api_delete(book_id: str):
    books.delete_book(book_id)
    return jsonify(deleted=True)


@bp.get("/api/settings")
def api_get_settings():
    return jsonify(books.get_settings())


@bp.post("/api/settings")
def api_save_settings():
    return jsonify(books.save_settings(_body()))


# ---------- audio of a converted book (see book_audio.py) ----------

def _book_language(book_id: str) -> str:
    from mining.languages import language_key
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
    body = _body()
    span = book_audio.find_sentence(book_id, str(body.get("sentence") or ""), _chapter(body.get("chapter")),
                                    _book_language(book_id))
    if span is None:
        return jsonify(found=False)
    return jsonify(found=True, url=f"/reader/api/books/{book_id}/audio/{span['track']}", **span)


# The sentence's audio cut as MP3, as a data URL for the card creator's "Sentence audio".
@bp.post("/api/books/<book_id>/audio/clip")
def api_audio_clip(book_id: str):
    import base64

    body = _body()
    span = book_audio.find_sentence(book_id, str(body.get("sentence") or ""), _chapter(body.get("chapter")),
                                    _book_language(book_id))
    if span is None:
        return jsonify(found=False)
    data = book_audio.clip(book_id, span["track"], span["start"], span["end"])
    return jsonify(found=True, data="data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii"),
                   name="sentence.mp3", **span)
