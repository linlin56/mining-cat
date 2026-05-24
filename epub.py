# epub.py — Split epub into per-chapter text files.

import json
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from config import DIR_CHAPTERS_TEXT, DIR_EBOOK, DIR_TEMP


def get_epub_file() -> Path:
    files = sorted(DIR_EBOOK.glob("*.epub"))
    if not files:
        raise FileNotFoundError(f"No .epub found in {DIR_EBOOK}")
    if len(files) > 1:
        print(f"Warning: multiple .epub files found, using: {files[0].name}")
    return files[0]

# Convert the content of an ebook item to plain text, stripping HTML tags and unnecessary whitespace.
def _item_to_text(item) -> str:
    try:
        content = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 1]
        return "\n".join(lines)
    except Exception:
        return ""

# href may have a fragment (e.g. "chapter1.html#section2"), but the spine items only reference the base file (e.g. "chapter1.html").
def _href_basename(href: str) -> str:
    return href.split("#")[0].rsplit("/", 1)[-1]

def _extract_title_from_text(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines and len(lines[0]) < 60:
        return lines[0]
    return ""

# Get the top-level TOC entries (those that are direct children of the book's TOC) as a list of epub.Link objects.
def _get_top_level_toc(book) -> list:
    links = []
    for entry in book.toc:
        if isinstance(entry, epub.Link):
            links.append(entry)
        elif isinstance(entry, tuple) and len(entry) >= 1:
            section = entry[0]
            if hasattr(section, "href"):
                links.append(epub.Link(section.href, section.title, ""))
    return links


def _get_spine_documents(book) -> list:
    items = []
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item and item.get_type() == ebooklib.ITEM_DOCUMENT:
            items.append(item)
    return items

def _find_spine_idx(spine_items: list, href: str) -> int:
    target = _href_basename(href)
    for i, item in enumerate(spine_items):
        basename = item.file_name.rsplit("/", 1)[-1]
        if basename == target or item.file_name == href or item.file_name.endswith("/" + href):
            return i
    return -1


def extract_chapters(book) -> list[tuple[str, str]]:
    # Extract chapters from the TOC, including spine items that fall between
    # two TOC entries but are not referenced by the TOC (orphan items).
    # Falls back to one-item-per-chapter if no TOC is present.
    toc_links = _get_top_level_toc(book)
    spine_items = _get_spine_documents(book)

    if not toc_links:
        result = []
        for i, item in enumerate(spine_items, 1):
            text = _item_to_text(item)
            if text:
                result.append((f"Section {i}", text))
        return result

    toc_starts = []
    toc_referenced_idxs = set()
    for link in toc_links:
        # Get index of spine item for this TOC entry
        idx = _find_spine_idx(spine_items, link.href)
        # If found, add to list of chapter starts and mark this index as referenced by the TOC
        if idx != -1:
            toc_starts.append((idx, link.title))
            toc_referenced_idxs.add(idx)
    toc_starts.sort(key=lambda x: x[0])

    all_starts = list(toc_starts)
    for j in range(len(toc_starts) - 1):
        start_idx = toc_starts[j][0]
        end_idx = toc_starts[j + 1][0]
        # Handle any spine items between start_idx and end_idx that are not referenced by the TOC (orphans)
        for k in range(start_idx + 1, end_idx):
            if k not in toc_referenced_idxs:
                text = _item_to_text(spine_items[k])
                if len(text.strip()) > 100:
                    title = _extract_title_from_text(text) or f"[untitled spine {k}]"
                    all_starts.append((k, title))
    all_starts.sort(key=lambda x: x[0])

    chapters = []
    # For each chapter start, take the spine items from that start to the next one (or end of spine) and concatenate text to get chapter content.
    for j, (start_idx, title) in enumerate(all_starts):
        end_idx = all_starts[j + 1][0] if j + 1 < len(all_starts) else len(spine_items)
        texts = [_item_to_text(item) for item in spine_items[start_idx:end_idx]]
        text = "\n\n".join(t for t in texts if t)
        if text.strip():
            chapters.append((title, text))

    return chapters


def save_chapters(
    selected: list[tuple[str, str]],
    preview: bool = False,
) -> None:
    DIR_CHAPTERS_TEXT.mkdir(parents=True, exist_ok=True)
    DIR_TEMP.mkdir(parents=True, exist_ok=True)
# Remove old chapter text files before saving new ones, then save the selected chapters and a manifest JSON with metadata.
    for old in DIR_CHAPTERS_TEXT.glob("chapter_*.txt"):
        old.unlink()

    manifest = []
    print(f"Saving {len(selected)} chapter(s) to {DIR_CHAPTERS_TEXT}/\n")

    # Save each selected chapter as a text file
    for i, (title, text) in enumerate(selected, start=1):
        out_path = DIR_CHAPTERS_TEXT / f"chapter_{i:03d}.txt"
        out_path.write_text(text, encoding="utf-8")
        # Add metadata for this chapter to the manifest
        manifest.append({"index": i, "title": title, "file": out_path.name,
                          "chars": len(text), "words": len(text.split())})
        print(f"  Ch.{i:03d}  {len(text):>8,} chars  {title}")
        if preview:
            print(f"           {text[:120].replace(chr(10), ' ')!r}")

    (DIR_TEMP / "ebook_chapters.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(selected)} chapters saved.")
    print(f"  Manifest: temp/ebook_chapters.json")

# Run epub processing
def run(
    list_only: bool = False,
    range_str: str | None = None,
    chapters_str: str | None = None,
    preview: bool = False,
) -> None:
    epub_path = get_epub_file()
    print(f"Reading {epub_path.name} ...")

    book = epub.read_epub(epub_path)
    all_chapters = extract_chapters(book)

    print(f"  {len(all_chapters)} chapter(s) detected (TOC + orphan spine items)\n")
    print(f"{'#':>4}  {'Chars':>8}  Title")
    print("  " + "-" * 60)
    for i, (title, text) in enumerate(all_chapters, 1):
        print(f"  {i:>3}  {len(text):>8,}  {title}")
    print()

    if list_only:
        return

    selected = all_chapters
    if range_str:
        try:
            a, b = range_str.split("-")
            selected = all_chapters[int(a) - 1 : int(b)]
        except (ValueError, IndexError):
            print(f"Error: invalid --range: {range_str!r}  (expected format: A-B)")
            return
    elif chapters_str:
        try:
            idxs = [int(x) - 1 for x in chapters_str.split(",")]
            selected = [all_chapters[i] for i in idxs if 0 <= i < len(all_chapters)]
        except (ValueError, IndexError):
            print(f"Error: invalid --chapters: {chapters_str!r}")
            return

    if not selected:
        print("No chapters selected.")
        return

    save_chapters(selected, preview=preview)
