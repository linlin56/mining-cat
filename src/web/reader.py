# reader.py - Flask blueprint of the ebook reader: library, chapters, images, progress and settings.
# The page itself (templates/reader.html + static/reader.js) does the layout and the pagination.

from flask import Blueprint, jsonify, render_template, request, send_file

from web import books

bp = Blueprint("reader", __name__, url_prefix="/reader")


@bp.errorhandler(books.BookError)
def _book_error(exc: books.BookError):
    return jsonify(title="Reader", error=str(exc)), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.get("/")
@bp.get("/<book_id>")
def page(book_id: str | None = None):
    return render_template("reader.html")


@bp.get("/api/books")
def api_books():
    return jsonify(books=books.list_books(), extensions=list(books.BOOK_EXTENSIONS))


@bp.post("/api/books")
def api_import():
    added, errors = [], []
    for upload in request.files.getlist("files"):
        name = upload.filename or "book"
        try:
            meta = books.import_book(name, upload.read())
            added.append({"id": meta["id"], "title": meta["title"]})
        except books.BookError as exc:
            errors.append(f"{name}: {exc}")
        except Exception as exc:  # a broken file must not break the whole upload
            errors.append(f"{name}: could not be read ({exc})")
    return jsonify(added=added, errors=errors)


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
