"""The folders of the reader's library: books and comics sorted by the user, in folders that can hold folders.
Only their place is kept here (library/reader_folders.json): the books and comics stay where they are."""
import re
import secrets
import threading
import time

from miningcat.config.paths import paths
from miningcat.domain.library.errors import FolderError
from miningcat.infrastructure.files.json_files import read_json, write_json

KINDS = ("book", "comic")
MAX_NAME = 80

_ID = re.compile(r"[0-9a-f]{16}")
_lock = threading.RLock()


def _read() -> dict:
    data = read_json(paths.reader_folders, {})
    return {"folders": data.get("folders") or {}, "items": data.get("items") or {}}


def _key(kind: str, item_id: str) -> str:
    """The key of a book or a comic (its kind and id are checked: they come from the browser)."""
    if kind not in KINDS or not _ID.fullmatch(item_id or ""):
        raise FolderError("Unknown book or comic.")
    return f"{kind}:{item_id}"


def _name(name) -> str:
    name = " ".join(str(name or "").split())[:MAX_NAME]
    if not name:
        raise FolderError("A folder needs a name.")
    return name


def _check(data: dict, folder_id: str | None) -> None:
    if folder_id is not None and folder_id not in data["folders"]:
        raise FolderError("Unknown folder.")


def _inside(data: dict, folder_id: str | None, ancestor: str) -> bool:
    """Whether `folder_id` is `ancestor` or one of its folders, at any depth."""
    seen = set()
    while folder_id is not None and folder_id not in seen:
        if folder_id == ancestor:
            return True
        seen.add(folder_id)
        folder_id = data["folders"].get(folder_id, {}).get("parent")
    return False


def list_folders(language: str = "") -> dict:
    """The folders of the language studied (and those of none), {id: {name, parent, language, created}} (parent None:
    in the library), and where each item is, {"book:<id>": folder id}."""
    data = _read()
    folders = {fid: dict(f) for fid, f in data["folders"].items()
               if not language or f.get("language", "") in (language, "")}
    for folder in folders.values():
        if folder.get("parent") not in folders:  # a folder whose parent isn't shown is shown in the library
            folder["parent"] = None
    return {"folders": folders, "items": {k: fid for k, fid in data["items"].items() if fid in folders}}


def create_folder(name, language: str = "", parent: str | None = None) -> dict:
    with _lock:
        data = _read()
        _check(data, parent)
        folder_id = secrets.token_hex(8)
        data["folders"][folder_id] = {"name": _name(name), "parent": parent, "language": language, "created": time.time()}
        write_json(paths.reader_folders, data)
    return {"id": folder_id, **data["folders"][folder_id]}


def rename_folder(folder_id: str, name) -> dict:
    with _lock:
        data = _read()
        _check(data, folder_id)
        data["folders"][folder_id]["name"] = _name(name)
        write_json(paths.reader_folders, data)
    return {"id": folder_id, **data["folders"][folder_id]}


def delete_folder(folder_id: str) -> None:
    """Deletes a folder: what it held (books, comics and folders) goes up into its parent."""
    with _lock:
        data = _read()
        _check(data, folder_id)
        parent = data["folders"].pop(folder_id).get("parent")
        for folder in data["folders"].values():
            if folder.get("parent") == folder_id:
                folder["parent"] = parent
        for key, fid in list(data["items"].items()):
            if fid == folder_id:
                if parent is None:
                    del data["items"][key]
                else:
                    data["items"][key] = parent
        write_json(paths.reader_folders, data)


def move(items: list, folder_id: str | None) -> None:
    """Puts books, comics and folders ([{kind, id}], kind "book", "comic" or "folder") in a folder, or back in the
    library (folder_id None). A folder never goes into itself, nor into one of its folders."""
    with _lock:
        data = _read()
        _check(data, folder_id)
        for item in items or []:
            kind, item_id = (item or {}).get("kind"), (item or {}).get("id")
            if kind == "folder":
                if item_id not in data["folders"]:
                    raise FolderError("Unknown folder.")
                if _inside(data, folder_id, item_id):
                    raise FolderError("A folder can't go into itself, nor into one of its folders.")
                data["folders"][item_id]["parent"] = folder_id
            elif folder_id is None:
                data["items"].pop(_key(kind, item_id), None)
            else:
                data["items"][_key(kind, item_id)] = folder_id
        write_json(paths.reader_folders, data)


def forget(kind: str, item_id: str) -> None:
    """A book or comic deleted from the library leaves its folder."""
    replace(kind, item_id, None)


def replace(kind: str, item_id: str, new_id: str | None) -> None:
    """A book or comic whose id changed (new_id None: deleted) keeps (or leaves) its folder."""
    with _lock:
        data = _read()
        folder_id = data["items"].pop(_key(kind, item_id), None)
        if folder_id is None or new_id == item_id:
            return
        if new_id is not None:
            data["items"][_key(kind, new_id)] = folder_id
        write_json(paths.reader_folders, data)
