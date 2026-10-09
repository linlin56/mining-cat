"""The comics and manga of the reader's library: archives unpacked into pages once (library/comics/<id>)."""
import os
import re
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
    return path.suffix.lower().lstrip(".") in PAGE_EXTENSIONS + CONVERTED_EXTENSIONS


def import_stream(filename: str, stream, language: str | None = None) -> dict:
    """Imports an uploaded archive, written to disk as it arrives, then unpacked into the library."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ARCHIVE_EXTENSIONS:
        raise ComicError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(ARCHIVE_EXTENSIONS)})")
    comics_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=f".{ext}", dir=comics_dir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(stream, out, 1024 * 1024)
        if tmp.stat().st_size == 0:
            raise ComicError("The file is empty.")
        return import_file(tmp, title=Path(filename).stem, filename=Path(filename).name, language=language)
    finally:
        tmp.unlink(missing_ok=True)


def import_file(path: Path, title: str | None = None, filename: str | None = None, language: str | None = None) -> dict:
    comic_id = fingerprint(path)
    folder = comic_folder(comic_id)
    with lock:
        if (folder / "meta.json").exists():
            return get_meta(comic_id)
        shutil.rmtree(folder, ignore_errors=True)  # leftovers of an interrupted import
        try:
            pages = _unpack(path, folder / "pages")
            if not pages:
                raise ComicError("No images in this archive.")
            make_thumbnail(folder / "pages" / pages[0]["file"], folder / "thumb.jpg", THUMB_WIDTH)
            if language:
                write_json(folder / "prefs.json", {"language": language})
            write_json(folder / "meta.json", {
                "id": comic_id, "filename": filename or path.name, "title": title or path.stem,
                "added": time.time(), "pages": pages,
            })
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
    return get_meta(comic_id)


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
            "id": meta["id"], "title": meta["title"], "pages": len(meta["pages"]),
            "added": meta.get("added", 0), "opened": progress.get("updated", 0), "percent": progress.get("percent", 0),
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


