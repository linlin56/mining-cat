"""The folders of the reader's library (books and comics)."""
from flask import Blueprint, jsonify

from miningcat.application import study_language as studied
from miningcat.application.library import folders
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("library_folders", __name__, url_prefix="/reader")


# The folders of the language studied, and the folder of each book and comic sorted.
@bp.get("/api/folders")
def api_folders():
    return jsonify(folders.list_folders(studied.current() or ""))


# A new folder, in the library or in the folder `parent`.
@bp.post("/api/folders")
def api_create_folder():
    body = json_body()
    return jsonify(folder=folders.create_folder(body.get("name"), studied.current() or "", body.get("parent") or None))


@bp.post("/api/folders/<folder_id>")
def api_rename_folder(folder_id: str):
    return jsonify(folder=folders.rename_folder(folder_id, json_body().get("name")))


@bp.post("/api/folders/<folder_id>/delete")
def api_delete_folder(folder_id: str):
    folders.delete_folder(folder_id)
    return jsonify(deleted=True)


# Puts books, comics and folders ({"items": [{kind, id}], "folder": id}) in a folder, or back in the library
# (folder null).
@bp.post("/api/folders/move")
def api_move():
    body = json_body()
    folders.move(body.get("items") if isinstance(body.get("items"), list) else [], body.get("folder") or None)
    return jsonify(moved=True)
