# files.py - Files picked in the browser.
#
# A browser can't hand a file path to the server, so picked files are uploaded into a staging
# folder (sources/.staging/<kind>/). The browser then refers to every file by its path relative
# to the project root, and the pipeline copies them where it needs them, exactly as it does with
# files picked in the Tkinter GUI. Files already sitting in sources/audiobook or sources/ebook are
# preloaded, like in the Tkinter GUI.

import shutil
import threading
from pathlib import Path

from werkzeug.utils import secure_filename

from gui_components.constants import DIR_AUDIOBOOK, DIR_EBOOK, ROOT

DIR_SOURCES = ROOT / "sources"
DIR_STAGING = DIR_SOURCES / ".staging"
DIR_OUTPUT = ROOT / "output"

KINDS = ("audio", "ebook", "video")


class InvalidPathError(ValueError):
    pass


def staging_dir(kind: str) -> Path:
    if kind not in KINDS:
        raise InvalidPathError(f"Unknown file kind: {kind!r}")
    return DIR_STAGING / kind


def clear_staging() -> None:
    if DIR_STAGING.exists():
        shutil.rmtree(DIR_STAGING, ignore_errors=True)


def to_ref(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def describe(path: Path) -> dict:
    return {"path": to_ref(path), "name": path.name}


# Turns a path sent by the browser back into a Path, refusing anything outside `base`
# (the browser only ever gets paths the server gave it, but nothing should be trusted).
def resolve_ref(ref: str, base: Path | None = None, must_exist: bool = True) -> Path:
    base = base or DIR_SOURCES
    if not isinstance(ref, str) or not ref:
        raise InvalidPathError("Missing file path.")
    path = (ROOT / ref).resolve()
    if not path.is_relative_to(base.resolve()):
        raise InvalidPathError(f"Path outside of {base.name}/: {ref}")
    if must_exist and not path.is_file():
        raise InvalidPathError(f"File not found: {ref} (it may have been removed, pick it again)")
    return path


def resolve_refs(refs: list, base: Path | None = None) -> list[Path]:
    if not isinstance(refs, list):
        raise InvalidPathError("Expected a list of file paths.")
    return [resolve_ref(r, base) for r in refs]


def allowed(filename: str, extensions: list[str] | tuple[str, ...]) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in extensions


# Saves uploaded files (werkzeug FileStorage objects) into the staging folder of `kind`.
def save_uploads(kind: str, uploads, extensions) -> tuple[list[dict], list[str]]:
    target = staging_dir(kind)
    target.mkdir(parents=True, exist_ok=True)
    saved, rejected = [], []
    for upload in uploads:
        name = Path(upload.filename or "").name
        # secure_filename() drops non-ASCII characters (e.g. Chinese book titles): only fall back to it when needed.
        if not name or name.startswith(".") or "/" in name or "\\" in name:
            name = secure_filename(upload.filename or "")
        if not name or not allowed(name, extensions):
            rejected.append(upload.filename or "?")
            continue
        path = target / name
        upload.save(path)
        saved.append(describe(path))
    return saved, rejected


# Deletes a staged upload. Files living in sources/audiobook or sources/ebook are only
# dropped from the browser's list, never deleted (same as "Remove selection" in the Tkinter GUI).
def discard(ref: str) -> bool:
    path = resolve_ref(ref, must_exist=False)
    if path.is_relative_to(DIR_STAGING.resolve()) and path.is_file():
        path.unlink()
        return True
    return False


def preload() -> dict:
    from config import glob_audio_files

    audio = [describe(f) for f in glob_audio_files(DIR_AUDIOBOOK)] if DIR_AUDIOBOOK.exists() else []
    epubs = sorted(DIR_EBOOK.glob("*.epub")) if DIR_EBOOK.exists() else []
    txts = sorted(DIR_EBOOK.glob("*.txt")) if DIR_EBOOK.exists() else []
    if epubs:
        ebook = [epubs[0]]
    else:
        ebook = txts
    return {"audio": audio, "ebook": [describe(f) for f in ebook]}


# One EPUB, or one or several TXT files (one chapter per file): same rule as the Tkinter GUI.
def normalize_ebook_selection(paths: list[Path]) -> list[Path]:
    epubs = [p for p in paths if p.suffix.lower() == ".epub"]
    if epubs:
        return [epubs[0]]
    return sorted(paths)


def _read_chapters(ebook_files: list[Path]) -> list[tuple[str, str]]:
    if len(ebook_files) > 1:
        chapters = []
        for p in ebook_files:
            text = p.read_text(encoding="utf-8").strip()
            if text:
                chapters.append((p.stem, text))
        return chapters
    f = ebook_files[0]
    if f.suffix.lower() == ".txt":
        return [(f.stem, f.read_text(encoding="utf-8"))]
    from ebooklib import epub as ebooklib_epub
    import epub as epub_mod
    book = ebooklib_epub.read_epub(str(f))
    return epub_mod.extract_chapters(book)


_chapter_cache: dict[tuple, list[tuple[str, str]]] = {}
_chapter_lock = threading.Lock()


# Chapters (title, text) of the selected ebook file(s), cached by path and modification time
# since a book is read again for the chapter list, the frequency lists and the pipeline.
def load_chapters(ebook_files: list[Path]) -> list[tuple[str, str]]:
    if not ebook_files:
        return []
    key = tuple((str(p), p.stat().st_mtime_ns) for p in ebook_files)
    with _chapter_lock:
        cached = _chapter_cache.get(key)
    if cached is not None:
        return cached
    chapters = _read_chapters(ebook_files)
    with _chapter_lock:
        _chapter_cache.clear()  # only the current book is worth keeping
        _chapter_cache[key] = chapters
    return chapters


def clear_output() -> None:
    if DIR_OUTPUT.exists():
        shutil.rmtree(DIR_OUTPUT)
    DIR_OUTPUT.mkdir(parents=True, exist_ok=True)
