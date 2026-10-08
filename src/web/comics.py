import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath

from web import books, videos

ARCHIVE_EXTENSIONS = ("cbz", "zip", "cbr", "rar", "cb7", "7z", "cbt", "tar")
_ZIP_EXTENSIONS = ("cbz", "zip")
# Pages the browser shows as they are; other images are converted to PNG on import.
PAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")
_CONVERTED_EXTENSIONS = ("bmp", "tif", "tiff", "avif", "jxl")
THUMB_WIDTH = 360
# Bump when the OCR's output changes: pages read with an older version are read again.
OCR_VERSION = 1
# Languages whose comics read right to left by default (manga, and their Chinese editions).
RIGHT_TO_LEFT_LANGUAGES = ("ja", "zh", "yue")

_DIGITS = re.compile(r"(\d+)")


class ComicError(ValueError):
    pass


_lock = threading.RLock()


def comics_dir() -> Path:
    return books.DIR_LIBRARY / "comics"


def _comic_dir(comic_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", comic_id or ""):
        raise ComicError("Unknown comic.")
    return comics_dir() / comic_id


# ---------------------------------------------------------------- import

def is_archive(filename: str) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in ARCHIVE_EXTENSIONS


def _natural_key(name: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(name)]


def _is_page(name: str) -> bool:
    path = Path(name)
    if any(part.startswith(".") or part == "__MACOSX" for part in path.parts):
        return False
    return path.suffix.lower().lstrip(".") in PAGE_EXTENSIONS + _CONVERTED_EXTENSIONS


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
    comic_id = videos.fingerprint(path)
    folder = _comic_dir(comic_id)
    with _lock:
        if (folder / "meta.json").exists():
            return get_meta(comic_id)
        shutil.rmtree(folder, ignore_errors=True)  # leftovers of an interrupted import
        try:
            pages = _unpack(path, folder / "pages")
            if not pages:
                raise ComicError("No images in this archive.")
            _make_thumb(folder / "pages" / pages[0]["file"], folder / "thumb.jpg")
            if language:
                books._write_json(folder / "prefs.json", {"language": language})
            books._write_json(folder / "meta.json", {
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
        if archive.suffix.lower().lstrip(".") in _ZIP_EXTENSIONS or zipfile.is_zipfile(archive):
            _unzip(archive, tmp)
        else:
            _untar(archive, tmp)
        names = sorted((str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file() and _is_page(str(p.relative_to(tmp)))),
                       key=_natural_key)
        target.mkdir(parents=True, exist_ok=True)
        return [page for i, name in enumerate(names, 1) if (page := _add_page(tmp / name, target, i)) is not None]


def _unzip(archive: Path, target: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir() or not _is_page(info.filename):
                    continue
                # the archive's paths are never trusted as they are: no absolute paths, no "..", no drive letters
                parts = [p for p in PurePosixPath(info.filename.replace("\\", "/")).parts if p not in ("", "/", "..") and ":" not in p]
                if not parts:
                    continue
                dest = target.joinpath(*parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile:
        raise ComicError("This archive is damaged, or isn't a ZIP archive.")


# RAR, 7z and tar archives: the bsdtar of macOS (libarchive) reads them; elsewhere it may need installing.
def _untar(archive: Path, target: Path) -> None:
    tool = shutil.which("bsdtar") or shutil.which("tar")
    if tool is None:
        raise ComicError("Unpacking this archive needs bsdtar (libarchive). Convert it to .cbz, or install bsdtar.")
    result = subprocess.run([tool, "-xf", str(archive), "-C", str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise ComicError(f"This archive couldn't be unpacked{': ' + detail[-1] if detail else ''}. Try converting it to .cbz.")
    # the extracted names come from the archive: drop anything that escaped the folder (absolute paths, links)
    root = target.resolve()
    for path in list(target.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            path.unlink(missing_ok=True)


def _add_page(source: Path, target: Path, number: int) -> dict | None:
    from PIL import Image

    ext = source.suffix.lower().lstrip(".")
    try:
        with Image.open(source) as img:
            width, height = img.size
            if ext in _CONVERTED_EXTENSIONS:
                name = f"{number:04d}.png"
                img.convert("RGB").save(target / name)
                return {"file": name, "width": width, "height": height}
    except (OSError, ValueError, Image.DecompressionBombError):
        return None  # not an image after all: skipped
    name = f"{number:04d}.{'jpg' if ext == 'jpeg' else ext}"
    shutil.move(source, target / name)
    return {"file": name, "width": width, "height": height}


def _make_thumb(page: Path, target: Path) -> None:
    from PIL import Image

    with Image.open(page) as img:
        img = img.convert("RGB")
        img.thumbnail((THUMB_WIDTH, THUMB_WIDTH * 2))
        img.save(target, "JPEG", quality=85)


# ---------------------------------------------------------------- library

def get_meta(comic_id: str) -> dict:
    meta = books._read_json(_comic_dir(comic_id) / "meta.json", None)
    if meta is None:
        raise ComicError("Unknown comic.")
    return meta


def list_comics() -> list[dict]:
    if not comics_dir().exists():
        return []
    comics = []
    for folder in comics_dir().iterdir():
        meta = books._read_json(folder / "meta.json", None)
        if meta is None:
            continue
        progress = get_progress(folder.name)
        comics.append({
            "id": meta["id"], "title": meta["title"], "pages": len(meta["pages"]),
            "added": meta.get("added", 0), "opened": progress.get("updated", 0), "percent": progress.get("percent", 0),
            "language": get_prefs(folder.name).get("language") or "",
        })
    comics.sort(key=lambda c: (c["opened"] or 0, c["added"] or 0), reverse=True)
    return comics


def page_path(comic_id: str, number: int) -> Path:
    meta = get_meta(comic_id)
    if not 1 <= number <= len(meta["pages"]):
        raise ComicError("No such page.")
    return _comic_dir(comic_id) / "pages" / meta["pages"][number - 1]["file"]


def thumb_path(comic_id: str) -> Path:
    path = _comic_dir(comic_id) / "thumb.jpg"
    if not path.is_file():
        raise ComicError("No thumbnail.")
    return path


def delete_comic(comic_id: str) -> None:
    folder = _comic_dir(comic_id)
    with _lock:
        if folder.exists():
            shutil.rmtree(folder)


# ---------------------------------------------------------------- progress, preferences, settings

def get_progress(comic_id: str) -> dict:
    return books._read_json(_comic_dir(comic_id) / "progress.json", {})


def save_progress(comic_id: str, page) -> dict:
    count = len(get_meta(comic_id)["pages"])
    try:
        page = max(1, min(count, int(page)))
    except (TypeError, ValueError):
        raise ComicError("Invalid page.")
    progress = {"page": page, "percent": round(page / count * 100, 2), "updated": time.time()}
    books._write_json(_comic_dir(comic_id) / "progress.json", progress)
    return progress


def get_prefs(comic_id: str) -> dict:
    return books._read_json(_comic_dir(comic_id) / "prefs.json", {})


def save_prefs(comic_id: str, values: dict) -> dict:
    get_meta(comic_id)
    prefs = get_prefs(comic_id)
    if "language" in values:
        language = str(values["language"] or "").strip()
        if language and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", language):
            raise ComicError("Invalid language tag.")
        prefs["language"] = language
    if "direction" in values:
        if values["direction"] not in ("", "rtl", "ltr"):
            raise ComicError("Invalid reading direction.")
        prefs["direction"] = values["direction"]
    books._write_json(_comic_dir(comic_id) / "prefs.json", prefs)
    return prefs


DEFAULT_SETTINGS = {
    "spread": "auto",     # "single", "double", or "auto" (two pages side by side when the window is wide)
    "first_single": True, # in two-page spreads, the cover stands alone (so that the spreads match the printed book)
    "text": "hover",      # OCR text over the page: "hover" (shown under the cursor), "always", or "boxes" (outlined)
    "colors": "status",   # words coloured by status when the text is shown, or "off"
}
_CHOICES = {"spread": ("auto", "single", "double"), "text": ("hover", "always", "boxes"), "colors": ("status", "off")}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **books._read_json(books.DIR_LIBRARY / "comic_settings.json", {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        if isinstance(default, bool):
            settings[key] = bool(values[key])
        elif values[key] in _CHOICES[key]:
            settings[key] = values[key]
    books._write_json(books.DIR_LIBRARY / "comic_settings.json", settings)
    return settings


def right_to_left(comic_id: str, language: str) -> bool:
    from miningcat.domain.languages import language_key

    direction = get_prefs(comic_id).get("direction")
    if direction:
        return direction == "rtl"
    return language_key(language) in RIGHT_TO_LEFT_LANGUAGES


# ---------------------------------------------------------------- text of the pages

def ocr_language(tag: str):
    """The OCR language (Language) of a text tagged `tag`: zh-Hans reads simplified characters."""
    from miningcat.domain.languages import LANGUAGES, Language, language_key

    lang = Language.for_tag(tag)
    if lang is None:
        key = language_key(tag)
        raise ComicError(f"Text recognition isn't available for {LANGUAGES.get(key, tag or 'this language')} yet.")
    return lang


def page_text(comic_id: str, number: int, language: str, again: bool = False) -> dict:
    """The text blocks of a page, read by OCR the first time (or `again`): {"blocks": [...], "engine_error"?}."""
    from miningcat.domain.languages import is_no_space, language_key
    from ocr_mining import layout
    from ocr_mining.dedup import is_plausible_text

    lang = ocr_language(language)
    path = page_path(comic_id, number)
    cache = _comic_dir(comic_id) / "ocr" / f"{number:04d}.json"
    data = None if again else books._read_json(cache, None)
    if not data or data.get("version") != OCR_VERSION or data.get("language") != lang.name:
        result = _worker.read(lang, path)
        data = {"version": OCR_VERSION, "language": lang.name, "width": result["width"], "height": result["height"],
                "lines": result["lines"]}
        books._write_json(cache, data)
    lines = [layout.Line(text, x, y, w, h) for text, x, y, w, h in data["lines"]]
    blocks = layout.group_lines(lines, right_to_left=right_to_left(comic_id, language))
    blocks = [b for b in blocks if is_plausible_text(layout.block_text(b, True), lang)]
    no_space = is_no_space(language_key(language))
    return {"blocks": layout.to_json(blocks, data["width"], data["height"], no_space)}


class _OcrWorker:
    """The OCR process (ocr_mining/worker.py), started on the first page read and kept for the next ones.
    One page at a time: it's restarted for another language, or when it died."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._language = None

    def read(self, language, image: Path) -> dict:
        from ocr_mining.worker import RESULT_PREFIX

        with self._lock:
            for attempt in range(2):
                proc = self._ensure(language)
                try:
                    proc.stdin.write(f"{image}\n")
                    proc.stdin.flush()
                    answer = self._answer(proc, RESULT_PREFIX)
                except (OSError, ComicError):
                    self._stop()
                    if attempt:
                        raise ComicError("The text recognition stopped unexpectedly.")
                    continue
                if "error" in answer:
                    raise ComicError(f"The text of this page couldn't be read: {answer['error']}")
                return answer
        raise ComicError("The text recognition stopped unexpectedly.")

    def _ensure(self, language) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None and self._language == language:
            return self._proc
        self._stop()
        from gui_components.constants import PYTHON, SRC_DIR
        from ocr_mining.worker import RESULT_PREFIX

        self._proc = subprocess.Popen(
            [PYTHON, str(SRC_DIR / "ocr_mining" / "worker.py"), language.name.lower()],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        self._language = language
        try:
            self._answer(self._proc, RESULT_PREFIX)  # {"ready": true}, once the engine is loaded
        except ComicError:
            self._stop()
            raise ComicError("The text recognition couldn't start (owocr needed: see `make install`).")
        return self._proc

    @staticmethod
    def _answer(proc: subprocess.Popen, prefix: str) -> dict:
        for line in proc.stdout:
            if line.startswith(prefix):
                return json.loads(line[len(prefix):])
        raise ComicError("The text recognition stopped unexpectedly.")

    def _stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._proc = None
        self._language = None


_worker = _OcrWorker()
