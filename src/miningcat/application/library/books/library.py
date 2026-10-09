"""The reader's library: books imported once (rendered to HTML chapters), their reading progress and preferences."""
import hashlib
import html
import re
import shutil
import threading
import time
from pathlib import Path

from miningcat.application.library.books.importers import importer_for
from miningcat.config.paths import paths
from miningcat.domain.library.errors import BookError
from miningcat.infrastructure.files.json_files import read_json, write_json

# Bump when the rendering changes: books imported with an older version are rendered again on access.
RENDER_VERSION = 1

BOOK_EXTENSIONS = ("epub", "txt", "html", "htm", "xhtml", "md")

_lock = threading.RLock()


def books_dir() -> Path:
    return paths.books


def book_folder(book_id: str) -> Path:
    """The folder of a book in the library (its id is checked: it comes from the browser)."""
    if not re.fullmatch(r"[0-9a-f]{16}", book_id or ""):
        raise BookError("Unknown book.")
    return books_dir() / book_id


def _render(book_dir: Path, book_id: str) -> dict:
    source = next(book_dir.glob("source.*"), None)
    if source is None:
        raise BookError("The book's file is missing from the library.")
    for sub in ("chapters", "res"):
        shutil.rmtree(book_dir / sub, ignore_errors=True)
    ext = source.suffix.lower().lstrip(".")
    old = read_json(book_dir / "meta.json", {})
    name = old.get("filename", source.name)
    meta = importer_for(ext).import_book(source, book_dir, book_id, name)
    if ext == "epub" and meta["title"] == source.stem:
        meta["title"] = Path(name).stem
    meta.update({
        "id": book_id,
        "filename": name,
        "added": old.get("added", time.time()),
        "render_version": RENDER_VERSION,
        "total_chars": sum(c["chars"] for c in meta["chapters"]),
    })
    write_json(book_dir / "meta.json", meta)
    return meta


def import_book(filename: str, data: bytes) -> dict:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in BOOK_EXTENSIONS:
        raise BookError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(BOOK_EXTENSIONS)})")
    book_id = hashlib.sha256(data).hexdigest()[:16]
    book_dir = book_folder(book_id)
    with _lock:
        if (book_dir / "meta.json").exists():
            return get_meta(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / f"source.{ext}").write_bytes(data)
        write_json(book_dir / "meta.json", {"filename": Path(filename).name, "added": time.time()})
        try:
            return _render(book_dir, book_id)
        except Exception:
            shutil.rmtree(book_dir, ignore_errors=True)
            raise


def get_meta(book_id: str) -> dict:
    book_dir = book_folder(book_id)
    with _lock:
        meta = read_json(book_dir / "meta.json", None)
        if meta is None:
            raise BookError("Unknown book.")
        if meta.get("render_version") != RENDER_VERSION:
            meta = _render(book_dir, book_id)
        return meta


def list_books() -> list[dict]:
    if not books_dir().exists():
        return []
    books = []
    for book_dir in books_dir().iterdir():
        if not (book_dir / "meta.json").exists():
            continue
        try:
            meta = get_meta(book_dir.name)
        except (BookError, OSError, ValueError):
            continue
        progress = get_progress(book_dir.name)
        books.append({
            "id": meta["id"], "title": meta["title"], "author": meta.get("author"),
            "language": meta["language"], "format": meta["format"], "cover": meta.get("cover"),
            "added": meta.get("added", 0), "percent": progress.get("percent", 0),
            "opened": progress.get("updated", 0),
        })
    books.sort(key=lambda b: (b["opened"] or 0, b["added"] or 0), reverse=True)
    return books


_BLOCK_END = re.compile(r"<(?:br\b[^>]*|/(?:p|div|li|h[1-6]|tr|blockquote|dd|dt|figcaption))>", re.IGNORECASE)
_RUBY_TEXT = re.compile(r"<(rt|rp)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def chapter_text(book_id: str, index: int) -> str:
    """Plain text of a chapter, a line per paragraph, ruby annotations left out (as the reader reads it)."""
    fragment = _BLOCK_END.sub("\n", _RUBY_TEXT.sub("", chapter_html(book_id, index)))
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def chapter_html(book_id: str, index: int) -> str:
    meta = get_meta(book_id)
    if not 0 <= index < len(meta["chapters"]):
        raise BookError("No such chapter.")
    return (book_folder(book_id) / "chapters" / f"{index:04d}.html").read_text(encoding="utf-8")


def resource_path(book_id: str, ref: str) -> Path:
    res_dir = (book_folder(book_id) / "res").resolve()
    path = (res_dir / ref).resolve()
    if not path.is_relative_to(res_dir) or not path.is_file():
        raise BookError("No such resource.")
    return path


def delete_book(book_id: str) -> None:
    book_dir = book_folder(book_id)
    with _lock:
        if book_dir.exists():
            shutil.rmtree(book_dir)


def get_progress(book_id: str) -> dict:
    return read_json(book_folder(book_id) / "progress.json", {})


def save_progress(book_id: str, chapter, offset, percent) -> dict:
    meta = get_meta(book_id)
    try:
        chapter = max(0, min(int(chapter), len(meta["chapters"]) - 1))
        offset = max(0, int(offset))
        percent = max(0.0, min(100.0, float(percent)))
    except (TypeError, ValueError):
        raise BookError("Invalid position.")
    progress = {"chapter": chapter, "offset": offset, "percent": round(percent, 2), "updated": time.time()}
    write_json(book_folder(book_id) / "progress.json", progress)
    return progress


_PREF_KEYS = {"writing": ("auto", "horizontal", "vertical"), "language": None}


def get_prefs(book_id: str) -> dict:
    return read_json(book_folder(book_id) / "prefs.json", {})


def save_prefs(book_id: str, prefs: dict) -> dict:
    get_meta(book_id)
    current = get_prefs(book_id)
    if "writing" in prefs and prefs["writing"] in _PREF_KEYS["writing"]:
        current["writing"] = prefs["writing"]
    if "language" in prefs:
        lang = str(prefs["language"] or "").strip()
        if lang and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", lang):
            raise BookError("Invalid language tag.")
        current["language"] = lang
    write_json(book_folder(book_id) / "prefs.json", current)
    return current


