"""The reader's books."""
from flask import Blueprint, jsonify, render_template, request, send_file

from miningcat.application import study_language as studied
from miningcat.application.library import books
from miningcat.application.mining import comprehension
from miningcat.domain.languages import LANGUAGES, language_key, same_family
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("books", __name__, url_prefix="/reader")


@bp.get("/")
@bp.get("/<book_id>")
def page(book_id: str | None = None):
    return render_template("reader.html")


def _language_of(book_id: str, declared: str | None) -> str:
    """The language of a book: the one the user set, else the one it declared or was detected."""
    return language_key(books.get_prefs(book_id).get("language") or declared)


# Only the books of the language studied (and those of no known language) are in the library.
@bp.get("/api/books")
def api_books():
    study = studied.current()
    shown = [b for b in books.list_books() if not study or _language_of(b["id"], b["language"]) in (study, "")]
    return jsonify(books=shown, extensions=list(books.BOOK_EXTENSIONS))


@bp.post("/api/books")
def api_import():
    study = studied.current()
    added, errors, elsewhere = [], [], []
    for upload in request.files.getlist("files"):
        name = upload.filename or "book"
        try:
            meta = books.import_book(name, upload.read())
            language = _language_of(meta["id"], meta["language"])
            # Detection can't tell Cantonese from Mandarin: a Chinese book belongs to the Chinese language studied.
            if study and language != study and (not language or same_family(language, study)):
                books.save_prefs(meta["id"], {"language": studied.default_tag(study)})
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
    body = json_body()
    return jsonify(books.save_progress(book_id, body.get("chapter"), body.get("offset"), body.get("percent")))


@bp.post("/api/books/<book_id>/prefs")
def api_prefs(book_id: str):
    return jsonify(books.save_prefs(book_id, json_body()))


# Share of the book's words the user knows, and its recommended (i+1) sentences (see application/mining/comprehension.py).
@bp.get("/api/books/<book_id>/comprehension")
def api_comprehension(book_id: str):
    meta = books.get_meta(book_id)
    language = _language_of(book_id, meta["language"])
    if not language:
        return jsonify(comprehension=None)
    path = books.book_folder(book_id) / "comprehension.json"
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
    return jsonify(books.save_settings(json_body()))
