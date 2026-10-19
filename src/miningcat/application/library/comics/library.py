"""The comics and manga of the reader's library: archives unpacked into pages once (library/comics/<id>).
A single picture is imported the same way, as a comic of one page; pictures put together make an album."""
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from miningcat.application.library.videos.importing import fingerprint
from miningcat.config.paths import paths
from miningcat.domain.library.errors import ComicError
from miningcat.infrastructure.files.archives import ArchiveError, untar, unzip
from miningcat.infrastructure.files.json_files import read_json, write_json
from miningcat.infrastructure.media.images import CONVERTED_EXTENSIONS, add_page, make_thumbnail

ARCHIVE_EXTENSIONS = ("cbz", "zip", "cbr", "rar", "cb7", "7z", "cbt", "tar")
_ZIP_EXTENSIONS = ("cbz", "zip")
# Pages the browser shows as they are; other images are converted to PNG on import.
PAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")
IMAGE_EXTENSIONS = PAGE_EXTENSIONS + CONVERTED_EXTENSIONS
IMPORT_EXTENSIONS = ARCHIVE_EXTENSIONS + IMAGE_EXTENSIONS
THUMB_WIDTH = 360

_DIGITS = re.compile(r"(\d+)")

lock = threading.RLock()


def comics_dir() -> Path:
    return paths.comics


def comic_folder(comic_id: str) -> Path:
    """The folder of a comic (its id is checked: it comes from the browser)."""
    if not re.fullmatch(r"[0-9a-f]{16}", comic_id or ""):
        raise ComicError("Unknown comic.")
    return comics_dir() / comic_id


def is_archive(filename: str) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in ARCHIVE_EXTENSIONS


def _natural_key(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(name)]


def _is_page(name: str) -> bool:
    path = Path(name)
    if any(part.startswith(".") or part == "__MACOSX" for part in path.parts):
        return False
    return path.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS


def _is_image(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS


def import_stream(filename: str, stream, language: str | None = None) -> dict:
    """Imports an uploaded archive (or picture), written to disk as it arrives, then unpacked into the library."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in IMPORT_EXTENSIONS:
        raise ComicError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(IMPORT_EXTENSIONS)})")
    comics_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=f".{ext}", dir=comics_dir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(stream, out, 1024 * 1024)
        if tmp.stat().st_size == 0:
            raise ComicError("The file is empty.")
        return import_file(tmp, title=Path(filename).stem, filename=Path(filename).name, language=language, owned=True)
    finally:
        tmp.unlink(missing_ok=True)


def import_file(path: Path, title: str | None = None, filename: str | None = None, language: str | None = None,
                owned: bool = False) -> dict:
    """Imports an archive or a picture (owned: a file of ours, a picture is moved rather than copied). The meta returned
    says whether it's `new` (False: it was already in the library)."""
    comic_id = fingerprint(path)
    folder = comic_folder(comic_id)
    with lock:
        if (folder / "meta.json").exists():
            return {**get_meta(comic_id), "new": False}
        shutil.rmtree(folder, ignore_errors=True)  # leftovers of an interrupted import
        try:
            image = _is_image(path)
            pages = _add_image(path, folder / "pages", owned) if image else _unpack(path, folder / "pages")
            if not pages:
                raise ComicError("This file isn't an image." if image else "No images in this archive.")
            make_thumbnail(folder / "pages" / pages[0]["file"], folder / "thumb.jpg", THUMB_WIDTH)
            if language:
                write_json(folder / "prefs.json", {"language": language})
            write_json(folder / "meta.json", {
                "id": comic_id, "filename": filename or path.name, "title": title or path.stem,
                "added": time.time(), "pages": pages, "image": image,
            })
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return {**get_meta(comic_id), "new": True}


def _add_image(image: Path, target: Path, owned: bool) -> list[dict]:
    """The one page of a picture: moved when the file is ours (an upload), else copied."""
    target.mkdir(parents=True, exist_ok=True)
    if owned:
        page = add_page(image, target, 1)
        return [page] if page else []
    comics_dir().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=comics_dir()) as tmp:
        copy = Path(tmp) / f"page{image.suffix.lower()}"
        shutil.copyfile(image, copy)
        page = add_page(copy, target, 1)
    return [page] if page else []


def _unpack(archive: Path, target: Path) -> list[dict]:
    """Pages of the archive, in reading order (names sorted naturally: page2 before page10), as {file, width, height}."""
    comics_dir().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=comics_dir()) as tmp:
        tmp = Path(tmp)
        try:
            if archive.suffix.lower().lstrip(".") in _ZIP_EXTENSIONS or zipfile.is_zipfile(archive):
                unzip(archive, tmp, keep=_is_page)
            else:
                untar(archive, tmp)
        except ArchiveError as exc:
            raise ComicError(str(exc))
        names = sorted((str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file() and _is_page(str(p.relative_to(tmp)))),
                       key=_natural_key)
        target.mkdir(parents=True, exist_ok=True)
        return [page for i, name in enumerate(names, 1) if (page := add_page(tmp / name, target, i)) is not None]


def is_album(meta: dict) -> bool:
    """Whether pictures can be added to a comic: a picture, or an album of pictures (not an archive's comic)."""
    return bool(meta.get("image") or meta.get("album"))


def append_image(comic_id: str, image_id: str) -> dict:
    """Adds the picture `image_id` to the picture or album `comic_id`, as its last page; the picture leaves the
    library. The album keeps its progress and its language. A picture that becomes an album gets an id of its own:
    its id was the picture's fingerprint, and importing that picture again must give the picture, not the album."""
    if comic_id == image_id:
        raise ComicError("A picture can't be added to itself.")
    with lock:
        meta, image = get_meta(comic_id), get_meta(image_id)
        if not image.get("image"):
            raise ComicError("Only a picture can be added to an album.")
        if not is_album(meta):
            raise ComicError("Pictures can only be added to a picture or an album, not to a comic.")
        source = page_path(image_id, 1)
        number = len(meta["pages"]) + 1
        name = f"{number:04d}{source.suffix}"
        shutil.copyfile(source, comic_folder(comic_id) / "pages" / name)
        meta["pages"].append({**image["pages"][0], "file": name})
        folder = comic_folder(comic_id)
        progress = read_json(folder / "progress.json", None)
        if progress and progress.get("page"):
            progress["percent"] = round(progress["page"] / len(meta["pages"]) * 100, 2)
            write_json(folder / "progress.json", progress)
        if not meta.get("album"):
            meta["id"] = secrets.token_hex(8)
            folder = folder.rename(comic_folder(meta["id"]))
        meta.update(image=False, album=True)
        write_json(folder / "meta.json", meta)
        delete_comic(image_id)
    return meta


def get_meta(comic_id: str) -> dict:
    meta = read_json(comic_folder(comic_id) / "meta.json", None)
    if meta is None:
        raise ComicError("Unknown comic.")
    return meta


def list_comics() -> list[dict]:
    if not comics_dir().exists():
        return []
    comics = []
    for folder in comics_dir().iterdir():
        meta = read_json(folder / "meta.json", None)
        if meta is None:
            continue
        progress = read_json(folder / "progress.json", {})
        comics.append({
            "id": meta["id"], "title": meta["title"], "pages": len(meta["pages"]), "image": meta.get("image", False),
            "album": meta.get("album", False), "added": meta.get("added", 0), "opened": progress.get("updated", 0),
            "percent": progress.get("percent", 0),
            "language": read_json(folder / "prefs.json", {}).get("language") or "",
        })
    comics.sort(key=lambda c: (c["opened"] or 0, c["added"] or 0), reverse=True)
    return comics


def page_path(comic_id: str, number: int) -> Path:
    meta = get_meta(comic_id)
    if not 1 <= number <= len(meta["pages"]):
        raise ComicError("No such page.")
    return comic_folder(comic_id) / "pages" / meta["pages"][number - 1]["file"]


def thumb_path(comic_id: str) -> Path:
    path = comic_folder(comic_id) / "thumb.jpg"
    if not path.is_file():
        raise ComicError("No thumbnail.")
    return path


def delete_comic(comic_id: str) -> None:
    folder = comic_folder(comic_id)
    with lock:
        if folder.exists():
            shutil.rmtree(folder)


