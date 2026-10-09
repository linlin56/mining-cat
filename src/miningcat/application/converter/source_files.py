"""The files the converter starts from: sources/audiobook and sources/ebook, or files picked by the user."""
import shutil
import threading
from pathlib import Path
from typing import Callable

from miningcat.config.paths import paths
from miningcat.infrastructure.ebooks.epub_book import EpubBook
from miningcat.infrastructure.media.audio_files import glob_audio_files

Chapters = list[tuple[str, str]]


def sources() -> dict[str, list[Path]]:
    """The files already in sources/: its audio files, and its book (an EPUB, or text files)."""
    audio = glob_audio_files(paths.audiobook)
    epubs = sorted(paths.ebook.glob("*.epub")) if paths.ebook.exists() else []
    txts = sorted(paths.ebook.glob("*.txt")) if paths.ebook.exists() else []
    return {"audio": audio, "ebook": epubs[:1] or txts}


def normalize_ebook_selection(files: list[Path]) -> list[Path]:
    """One EPUB, or one or several text files (one chapter per file)."""
    epubs = [p for p in files if p.suffix.lower() == ".epub"]
    if epubs:
        return [epubs[0]]
    return sorted(files)


def read_chapters(ebook_files: list[Path]) -> Chapters:
    """(title, text) of the chapters of an EPUB, of a text file (one chapter), or of several text files."""
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
    return EpubBook.open(f).chapters()


class ChapterCache:
    """The chapters of the last book read: a book is read for its chapter list, its frequency lists and the
    pipeline. Kept until one of its files changes."""

    def __init__(self):
        self._key: tuple | None = None
        self._chapters: Chapters = []
        self._lock = threading.Lock()

    def load(self, ebook_files: list[Path]) -> Chapters:
        if not ebook_files:
            return []
        key = tuple((str(p), p.stat().st_mtime_ns) for p in ebook_files)
        with self._lock:
            if key == self._key:
                return self._chapters
        chapters = read_chapters(ebook_files)
        with self._lock:
            self._key, self._chapters = key, chapters
        return chapters


_chapters = ChapterCache()


def load_chapters(ebook_files: list[Path]) -> Chapters:
    return _chapters.load(ebook_files)


def _replace_files(files: list[Path], folder: Path, label: str, in_place: str, log: Callable[[str], None]) -> None:
    """Copies the files to a sources/ folder, emptied first, unless they're already there."""
    if not [f for f in files if f.parent != folder]:
        log(f"  {label} : {in_place}\n")
        return
    if folder.exists():
        for f in folder.iterdir():
            if f.is_file():
                f.unlink()
    else:
        folder.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, folder / f.name)
        log(f"  {label} : {f.name}\n")


def copy_sources(audio_files: list[Path], ebook_files: list[Path], log: Callable[[str], None]) -> None:
    """Puts the files picked by the user in sources/audiobook and sources/ebook, where the steps read them."""
    log("Copying source files\n")
    if audio_files:
        _replace_files(audio_files, paths.audiobook, "audio", "files already in place", log)
    if ebook_files:
        _replace_files(ebook_files, paths.ebook, "ebook", "file(s) already in place", log)


def clear_output() -> None:
    """Deletes everything the converter made (output/)."""
    if paths.output.exists():
        shutil.rmtree(paths.output)
    paths.output.mkdir(parents=True, exist_ok=True)
