from flask import Blueprint, jsonify, render_template, request, send_file

from web import book_audio, books, comics, profile

bp = Blueprint("reader", __name__, url_prefix="/reader")


@bp.errorhandler(books.BookError)
def _book_error(exc: books.BookError):
    return jsonify(title="Reader", error=str(exc)), 400


@bp.errorhandler(book_audio.AudioError)
def _audio_error(exc: book_audio.AudioError):
    return jsonify(title="Audio", error=str(exc)), 400


@bp.errorhandler(comics.ComicError)
def _comic_error(exc: comics.ComicError):
    return jsonify(title="Comics", error=str(exc)), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.get("/")
@bp.get("/<book_id>")
def page(book_id: str | None = None):
    return render_template("reader.html")


@bp.get("/comic/<comic_id>")
def comic_page(comic_id: str):
    return render_template("comic.html")


def _language_of(book_id: str, declared: str | None) -> str:
    from miningcat.domain.languages import language_key
    return language_key(books.get_prefs(book_id).get("language") or declared)


# Only the books of the language studied (and those of no known language) are in the library.
@bp.get("/api/books")
def api_books():
    study = profile.current()
    shown = [b for b in books.list_books() if not study or _language_of(b["id"], b["language"]) in (study, "")]
    return jsonify(books=shown, extensions=list(books.BOOK_EXTENSIONS))


@bp.post("/api/books")
def api_import():
    from miningcat.domain.languages import LANGUAGES, same_family

    study = profile.current()
    added, errors, elsewhere = [], [], []
    for upload in request.files.getlist("files"):
        name = upload.filename or "book"
        try:
            meta = books.import_book(name, upload.read())
            language = _language_of(meta["id"], meta["language"])
            # Detection can't tell Cantonese from Mandarin: a Chinese book belongs to the Chinese language studied.
            if study and language != study and (not language or same_family(language, study)):
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


# Share of the book's words the user knows, and its recommended (i+1) sentences (see mining/comprehension.py).
@bp.get("/api/books/<book_id>/comprehension")
def api_comprehension(book_id: str):
    from mining import comprehension

    meta = books.get_meta(book_id)
    language = _language_of(book_id, meta["language"])
    if not language:
        return jsonify(comprehension=None)
    path = books._book_dir(book_id) / "comprehension.json"
    texts = lambda: [books.chapter_text(book_id, i) for i in range(len(meta["chapters"]))]
    return jsonify(comprehension=comprehension.cached(path, language, [meta.get("render_version"), len(meta["chapters"])], texts))


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
    from miningcat.domain.languages import language_key
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


# ---------- comics and manga ----------

@bp.get("/api/comics")
def api_comics():
    from miningcat.domain.languages import language_key

    study = profile.current()
    shown = [c for c in comics.list_comics() if not study or language_key(c["language"]) in (study, "")]
    return jsonify(comics=shown, extensions=list(comics.ARCHIVE_EXTENSIONS))


# The archive is the request's body (a comic can be large): written to disk as it arrives.
@bp.post("/api/comics")
def api_import_comic():
    study = profile.current()
    name = request.args.get("name") or ""
    return jsonify(comic=comics.import_stream(name, request.stream, language=profile.default_tag(study) if study else None))


@bp.get("/api/comics/<comic_id>")
def api_comic(comic_id: str):
    return jsonify(comic=comics.get_meta(comic_id), progress=comics.get_progress(comic_id), prefs=comics.get_prefs(comic_id))


@bp.get("/api/comics/<comic_id>/pages/<int:number>")
def api_comic_page(comic_id: str, number: int):
    return send_file(comics.page_path(comic_id, number), max_age=86400)


# The text blocks of a page, read by OCR the first time it's asked for (`again`: read it again).
@bp.get("/api/comics/<comic_id>/pages/<int:number>/text")
def api_comic_text(comic_id: str, number: int):
    language = comics.get_prefs(comic_id).get("language") or profile.default_tag(profile.current())
    return jsonify(comics.page_text(comic_id, number, language, again=request.args.get("again") == "1"))


@bp.get("/api/comics/<comic_id>/thumb")
def api_comic_thumb(comic_id: str):
    return send_file(comics.thumb_path(comic_id), max_age=86400)


@bp.post("/api/comics/<comic_id>/delete")
def api_delete_comic(comic_id: str):
    comics.delete_comic(comic_id)
    return jsonify(deleted=True)


@bp.post("/api/comics/<comic_id>/progress")
def api_comic_progress(comic_id: str):
    return jsonify(comics.save_progress(comic_id, _body().get("page")))


@bp.post("/api/comics/<comic_id>/prefs")
def api_comic_prefs(comic_id: str):
    return jsonify(comics.save_prefs(comic_id, _body()))


@bp.get("/api/comic-settings")
def api_get_comic_settings():
    return jsonify(comics.get_settings())


@bp.post("/api/comic-settings")
def api_save_comic_settings():
    return jsonify(comics.save_settings(_body()))
