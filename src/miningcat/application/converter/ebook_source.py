from dataclasses import dataclass
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.infrastructure.ebooks.epub_book import EpubBook


@dataclass
class EbookSource:
    """The book of sources/ebook: an EPUB, a text file, or several text files (one chapter each)."""

    kind: str           # epub, txt or multi_txt
    files: list[Path]

    def chapters(self) -> list[tuple[str, str]]:
        """(title, text) of each chapter. A text file is one chapter, named after the file."""
        if self.kind == "epub":
            return EpubBook.open(self.files[0]).chapters()
        chapters = []
        for path in self.files:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                chapters.append((path.stem, text))
        return chapters


def find_ebook() -> EbookSource:
    """The book of sources/ebook. Raises FileNotFoundError without any."""
    epubs = sorted(paths.ebook.glob("*.epub"))
    if epubs:
        if len(epubs) > 1:
            print(f"Warning: multiple .epub files found, using: {epubs[0].name}")
        return EbookSource("epub", epubs[:1])
    txts = sorted(paths.ebook.glob("*.txt"))
    if not txts:
        raise FileNotFoundError(f"No .epub or .txt found in {paths.ebook}")
    return EbookSource("txt" if len(txts) == 1 else "multi_txt", txts)


def _epub() -> EpubBook | None:
    try:
        source = find_ebook()
    except FileNotFoundError:
        return None
    return EpubBook.open(source.files[0]) if source.kind == "epub" else None


def epub_title() -> str | None:
    """The title of the EPUB of sources/ebook, if any."""
    try:
        book = _epub()
        return book.title if book else None
    except Exception:
        return None


def epub_cover() -> Path | None:
    """The cover of the EPUB of sources/ebook, saved in output/temp (for the videos' background)."""
    book = _epub()
    content = book.cover() if book else None
    if not content:
        return None
    paths.temp.mkdir(parents=True, exist_ok=True)
    cover_path = paths.temp / "cover.jpg"
    cover_path.write_bytes(content)
    return cover_path
