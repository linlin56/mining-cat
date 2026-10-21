"""The comics and manga of the reader."""
from flask import Blueprint, jsonify, render_template, request, send_file

from miningcat.application import study_language as studied
from miningcat.application.library import comics, folders
from miningcat.application.mining import comprehension
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
    return jsonify(comics=shown, extensions=list(comics.ARCHIVE_EXTENSIONS), images=list(comics.IMAGE_EXTENSIONS))


# The archive (or picture) is the request's body (a comic can be large): written to disk as it arrives.
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


# Share of the comic's words the user knows, and its recommended (i+1) sentences (see application/mining/comprehension.py),
# once every page has its text: until then, the others are read by OCR in the background, and it's None (`read` of
# `pages` tells how far it is). `error`: why they can't be read. `failed`: pages the OCR couldn't read (tried again
# once), counted without text.
@bp.get("/api/comics/<comic_id>/comprehension")
def api_comic_comprehension(comic_id: str):
    pages = len(comics.get_meta(comic_id)["pages"])
    language = comics.get_prefs(comic_id).get("language") or studied.default_tag(studied.current())
    read, failed, version = comics.text_state(comic_id, language)
    if read < pages or failed:
        reading = comics.read_all_pages(comic_id, language, retry_failed=read == pages)
        error = comics.ocr_unavailable(comic_id, language)
        if reading or (error and read < pages):
            return jsonify(comprehension=None, read=read - failed, pages=pages, error=None if reading else error)
    path = comics.comic_folder(comic_id) / "comprehension.json"
    result = comprehension.cached(path, language_key(language), version, lambda: comics.page_texts(comic_id, language))
    return jsonify(comprehension=result, read=read, pages=pages, failed=failed)


@bp.get("/api/comics/<comic_id>/thumb")
def api_comic_thumb(comic_id: str):
    return send_file(comics.thumb_path(comic_id), max_age=86400)


@bp.post("/api/comics/<comic_id>/delete")
def api_delete_comic(comic_id: str):
    comics.delete_comic(comic_id)
    folders.forget("comic", comic_id)
    return jsonify(deleted=True)


# Drags a picture onto a picture (or an album): it becomes the album's last page.
@bp.post("/api/comics/<comic_id>/append")
def api_append_image(comic_id: str):
    image_id = str(json_body().get("image") or "")
    meta = comics.append_image(comic_id, image_id)
    folders.forget("comic", image_id)
    folders.replace("comic", comic_id, meta["id"])
    return jsonify(comic=meta)


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
