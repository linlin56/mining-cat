"""The text of comic pages, read by OCR (in its own process) the first time and kept next to the pages; or, for a PDF
with selectable text, the text it has (text/<number>.json, written on import), not read by OCR unless asked again."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from miningcat.application.library.comics.library import comic_folder, get_meta, lock, page_path
from miningcat.application.library.comics.progress import right_to_left
from miningcat.domain.languages import LANGUAGES, Language, is_no_space, language_key
from miningcat.domain.library.errors import ComicError
from miningcat.domain.ocr import layout
from miningcat.domain.ocr.plausibility import is_plausible_text
from miningcat.infrastructure.files.json_files import read_json, write_json
from miningcat.infrastructure.ocr.worker_client import OcrPageError, OcrWorker, OcrWorkerError

# Bump when the OCR's output changes: pages read with an older version are read again.
OCR_VERSION = 1

_worker = OcrWorker()


def ocr_language(tag: str):
    """The OCR language (Language) of a text tagged `tag`: zh-Hans reads simplified characters."""
    lang = Language.for_tag(tag)
    if lang is None:
        key = language_key(tag)
        raise ComicError(f"Text recognition isn't available for {LANGUAGES.get(key, tag or 'this language')} yet.")
    return lang


def _ocr_file(comic_id: str, number: int) -> Path:
    return comic_folder(comic_id) / "ocr" / f"{number:04d}.json"


def _pdf_file(comic_id: str, number: int) -> Path:
    return comic_folder(comic_id) / "text" / f"{number:04d}.json"


def _source(comic_id: str, number: int, language: str) -> tuple[Path, dict] | None:
    """Where the text of a page is, and that text: what the OCR read of it (with this version, in this language),
    else its PDF's. The OCR's comes first: it's there for a page of a PDF only when asked to read it again."""
    lang = Language.for_tag(language)
    if lang is not None:
        path = _ocr_file(comic_id, number)
        data = read_json(path, None)
        if data and data.get("version") == OCR_VERSION and data.get("language") == lang.name:
            return path, data
    path = _pdf_file(comic_id, number)
    data = read_json(path, None)
    return (path, data) if data is not None else None


# The pages the reader shows are read before those read in the background: a background read waits while one of
# them waits for the OCR (it then waits for the page being read, not more), and for READER_PAUSE seconds after the
# reader read one: while someone reads, the OCR is theirs, in their language (it restarts for another).
READER_PAUSE = 30
_shown_waiting = 0
_last_shown = float("-inf")
_turn = threading.Condition()


def _background_turn() -> bool:
    return not _shown_waiting and time.monotonic() - _last_shown >= READER_PAUSE


def _ocr(comic_id: str, number: int, lang: Language, background: bool = False) -> dict:
    global _shown_waiting, _last_shown
    path = page_path(comic_id, number)
    with _turn:
        if background:
            while not _turn.wait_for(_background_turn, timeout=5):
                pass
        else:
            _shown_waiting += 1
    try:
        result = _worker.read(lang, path)
    finally:
        if not background:
            with _turn:
                _shown_waiting -= 1
                _last_shown = time.monotonic()
                _turn.notify_all()
    data = {"version": OCR_VERSION, "language": lang.name, "width": result["width"], "height": result["height"],
            "lines": result["lines"]}
    _keep(comic_id, number, data)
    _ocr_works()
    return data


def _keep(comic_id: str, number: int, data: dict) -> None:
    """Writes what the OCR read of a page, unless the comic was removed (or became an album, of another id) meanwhile."""
    with lock:
        get_meta(comic_id)
        write_json(_ocr_file(comic_id, number), data)


def page_text(comic_id: str, number: int, language: str, again: bool = False) -> dict:
    """The text blocks of a page, read by OCR the first time (or `again`, a page of a PDF too): {"blocks": [...]}.
    A page the background reading couldn't read is read again when it's shown."""
    page_path(comic_id, number)  # the page exists
    source = None if again else _source(comic_id, number, language)
    data = source[1] if source else None
    if data is None or data.get("error"):
        try:
            data = _ocr(comic_id, number, ocr_language(language))
        except OcrWorkerError as exc:
            raise ComicError(str(exc)) from exc
    return {"blocks": _blocks(comic_id, data, language)}


def _blocks(comic_id: str, data: dict, language: str) -> list[dict]:
    lines = [layout.Line(text, x, y, w, h) for text, x, y, w, h in data["lines"]]
    blocks = layout.group_lines(lines, right_to_left=right_to_left(comic_id, language))
    lang = Language.for_tag(language)
    if lang is not None:  # noise read by the OCR (or a PDF's formulas): no letter of the language
        blocks = [b for b in blocks if is_plausible_text(layout.block_text(b, True), lang)]
    no_space = is_no_space(language_key(language))
    return layout.to_json(blocks, data["width"], data["height"], no_space)


# text_state() of each comic, kept while its text files don't change: {(comic id, language): (key, read, failed)}.
_states: dict[tuple[str, str], tuple[str, int, int]] = {}


def _files(comic_id: str) -> list:
    """The text files of a comic, as (folder, name, modification time): enough to tell its text changed."""
    entries = []
    for sub in ("ocr", "text"):
        try:
            with os.scandir(comic_folder(comic_id) / sub) as it:
                entries += [(sub, e.name, e.stat().st_mtime_ns) for e in it if e.name.endswith(".json")]
        except FileNotFoundError:
            pass
    return sorted(entries)


def text_state(comic_id: str, language: str) -> tuple[int, int, str]:
    """How many pages have their text (their PDF's, or read by OCR), how many of them the OCR couldn't read (they have
    none), and a key that changes with that text (a page read, or read again; another reading direction). The files
    are only read when they changed: see page_texts() for the text."""
    key = hashlib.sha1(json.dumps([OCR_VERSION, language, right_to_left(comic_id, language), _files(comic_id)])
                       .encode("utf-8")).hexdigest()
    known = _states.get((comic_id, language))
    if known and known[0] == key:
        return known[1], known[2], key
    read = failed = 0
    for number in range(1, len(get_meta(comic_id)["pages"]) + 1):
        source = _source(comic_id, number, language)
        if source is not None:
            read += 1
            failed += bool(source[1].get("error"))
    _states[(comic_id, language)] = (key, read, failed)
    return read, failed, key


def page_texts(comic_id: str, language: str) -> list[str]:
    """The text of the pages that have some (a line per block, as the reader shows them)."""
    texts = []
    for number in range(1, len(get_meta(comic_id)["pages"]) + 1):
        source = _source(comic_id, number, language)
        if source is not None:
            texts.append("\n".join(block["text"] for block in _blocks(comic_id, source[1], language)))
    return texts


# The background reading: one comic after the other (the OCR reads one page at a time, in one language), and why a
# comic can't be read: {(comic id, language): (message, until)}, until None when there's no OCR for its language;
# else the OCR failed, and it's tried again after RETRY_AFTER seconds (or as soon as it reads a page again).
RETRY_AFTER = 300
_queue: list[tuple[str, str, bool]] = []
_unavailable: dict[tuple[str, str], tuple[str, float | None]] = {}
_retried: set[tuple[str, str]] = set()
_queue_lock = threading.Lock()
_reader: threading.Thread | None = None


def read_all_pages(comic_id: str, language: str, retry_failed: bool = False) -> bool:
    """Reads the pages without text yet in the background (for the comic's comprehension); `retry_failed`: the pages
    the OCR couldn't read too, once. Whether they're being read: see ocr_unavailable() when they can't be."""
    global _reader
    try:
        ocr_language(language)
    except ComicError as exc:
        _unavailable[(comic_id, language)] = (str(exc), None)
        return False
    with _queue_lock:
        if any(q[:2] == (comic_id, language) for q in _queue):
            return True
        if ocr_unavailable(comic_id, language) or retry_failed and (comic_id, language) in _retried:
            return False
        if retry_failed:
            _retried.add((comic_id, language))
        _queue.append((comic_id, language, retry_failed))
        if _reader is None:
            _reader = threading.Thread(target=_read_queue, name="ocr-background", daemon=True)
            _reader.start()
    return True


def ocr_unavailable(comic_id: str, language: str) -> str | None:
    """Why the pages of a comic can't be read by OCR (no OCR for its language, or the OCR doesn't work), if so."""
    entry = _unavailable.get((comic_id, language))
    if entry is None:
        return None
    message, until = entry
    if until is not None and time.monotonic() >= until:
        _unavailable.pop((comic_id, language), None)
        return None
    return message


def _ocr_works() -> None:
    for key, (_, until) in list(_unavailable.items()):
        if until is not None:
            _unavailable.pop(key, None)


def _read_queue() -> None:
    global _reader
    language = None
    try:
        while True:
            with _queue_lock:
                if not _queue:
                    _reader = None  # in the lock: a comic queued from now on starts another reader
                    return
                # the comics in the language the OCR has loaded first
                item = next((q for q in _queue if q[1] == language), _queue[0])
            try:
                _read_comic(*item)
            finally:
                with _queue_lock:
                    _queue.remove(item)
            language = item[1]
    finally:
        with _queue_lock:
            if _reader is threading.current_thread():  # stopped by an unexpected error
                _reader = None


def _read_comic(comic_id: str, language: str, retry_failed: bool) -> None:
    lang = ocr_language(language)
    try:
        pages = get_meta(comic_id)["pages"]
        for number, page in enumerate(pages, 1):
            source = _source(comic_id, number, language)
            if source is not None and not (retry_failed and source[1].get("error")):
                continue
            try:
                _ocr(comic_id, number, lang, background=True)
            except OcrPageError as exc:
                # kept as a page without text (read again when it's shown), not to stop the comic's comprehension
                _keep(comic_id, number, {
                    "version": OCR_VERSION, "language": lang.name, "width": page["width"], "height": page["height"],
                    "lines": [], "error": str(exc)})
    except OcrWorkerError as exc:
        _unavailable[(comic_id, language)] = (str(exc), time.monotonic() + RETRY_AFTER)
    except ComicError:
        pass  # removed meanwhile
