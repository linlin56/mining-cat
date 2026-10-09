"""Step 2 of an audiobook: the text of its book, one file per chapter in output/chapters_text."""
import json

from miningcat.application.converter.ebook_source import EbookSource, find_ebook
from miningcat.application.converter.errors import ConverterError
from miningcat.config.paths import paths
from miningcat.domain.ebook.chapter_selection import SelectionError, select_chapters

MANIFEST_NAME = "ebook_chapters.json"


def save_chapters(selected: list[tuple[str, str]], preview: bool = False) -> None:
    """Writes the chapters to output/chapters_text (replacing the previous ones), and their manifest."""
    paths.chapters_text.mkdir(parents=True, exist_ok=True)
    paths.temp.mkdir(parents=True, exist_ok=True)
    for old in paths.chapters_text.glob("chapter_*.txt"):
        old.unlink()

    manifest = []
    print(f"Saving {len(selected)} chapter(s) to {paths.chapters_text}/\n")
    for i, (title, text) in enumerate(selected, start=1):
        out_path = paths.chapters_text / f"chapter_{i:03d}.txt"
        out_path.write_text(text, encoding="utf-8")
        manifest.append({"index": i, "title": title, "file": out_path.name,
                         "chars": len(text), "words": len(text.split())})
        print(f"  Ch.{i:03d}  {len(text):>8,} chars  {title}")
        if preview:
            print(f"           {text[:120].replace(chr(10), ' ')!r}")

    (paths.temp / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(selected)} chapters saved.")
    print(f"  Manifest: temp/{MANIFEST_NAME}")


def _describe(source: EbookSource, chapters: list[tuple[str, str]]) -> None:
    if source.kind == "epub":
        print(f"Reading {source.files[0].name} ...")
        print(f"  {len(chapters)} chapter(s) detected (TOC + orphan spine items)\n")
    elif source.kind == "txt":
        print(f"Reading {source.files[0].name} ...")
        print("  1 chapter (full text - no chapter info in .txt)\n")
    else:
        print(f"Found {len(source.files)} .txt files - each treated as a chapter.\n")
    print(f"{'#':>4}  {'Chars':>8}  Title")
    print("  " + "-" * 60)
    for i, (title, text) in enumerate(chapters, 1):
        print(f"  {i:>3}  {len(text):>8,}  {title}")
    print()


def run(list_only: bool = False, range_str: str | None = None, chapters_str: str | None = None,
        preview: bool = False) -> None:
    """Extracts the chapters of the book of sources/ebook (all of them, or a range or list of them)."""
    try:
        source = find_ebook()
    except FileNotFoundError as exc:
        raise ConverterError(str(exc))
    chapters = source.chapters()
    if source.kind == "txt" and not chapters:
        raise ConverterError("text file is empty.")
    _describe(source, chapters)
    if list_only:
        return
    try:
        selected = select_chapters(chapters, range_str, chapters_str) if source.kind != "txt" else chapters
    except SelectionError as exc:
        raise ConverterError(str(exc))
    if not selected:
        raise ConverterError("No chapters selected.")
    save_chapters(selected, preview=preview)
