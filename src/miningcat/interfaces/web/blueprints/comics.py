"""The comics and manga of the reader."""
from flask import Blueprint, jsonify, render_template, request, send_file

from miningcat.application import study_language as studied
from miningcat.application.library import comics
from miningcat.domain.languages import language_key
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("comics", __name__, url_prefix="/reader")


@bp.get("/comic/<comic_id>")
def comic_page(comic_id: str):
    return render_template("comic.html")

@bp.get("/api/comics")
def api_comics():
    study = studied.current()
    shown = [c for c in comics.list_comics() if not study or language_key(c["language"]) in (study, "")]
    return jsonify(comics=shown, extensions=list(comics.ARCHIVE_EXTENSIONS))


# The archive is the request's body (a comic can be large): written to disk as it arrives.
@bp.post("/api/comics")
def api_import_comic():
    study = studied.current()
    name = request.args.get("name") or ""
    return jsonify(comic=comics.import_stream(name, request.stream, language=studied.default_tag(study) if study else None))


@bp.get("/api/comics/<comic_id>")
def api_comic(comic_id: str):
    return jsonify(comic=comics.get_meta(comic_id), progress=comics.get_progress(comic_id), prefs=comics.get_prefs(comic_id))


@bp.get("/api/comics/<comic_id>/pages/<int:number>")
def api_comic_page(comic_id: str, number: int):
    return send_file(comics.page_path(comic_id, number), max_age=86400)


# The text blocks of a page, read by OCR the first time it's asked for (`again`: read it again).
@bp.get("/api/comics/<comic_id>/pages/<int:number>/text")
def api_comic_text(comic_id: str, number: int):
    language = comics.get_prefs(comic_id).get("language") or studied.default_tag(studied.current())
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
    return jsonify(comics.save_progress(comic_id, json_body().get("page")))


@bp.post("/api/comics/<comic_id>/prefs")
def api_comic_prefs(comic_id: str):
    return jsonify(comics.save_prefs(comic_id, json_body()))


@bp.get("/api/comic-settings")
def api_get_comic_settings():
    return jsonify(comics.get_settings())


@bp.post("/api/comic-settings")
def api_save_comic_settings():
    return jsonify(comics.save_settings(json_body()))
