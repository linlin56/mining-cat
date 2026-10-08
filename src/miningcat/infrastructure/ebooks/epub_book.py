from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub


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


def _extract_chapters(book) -> list[tuple[str, str]]:
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



class EpubBook:
    """An EPUB file, read with ebooklib: its chapters as plain text, its title and its cover."""

    def __init__(self, book):
        self._book = book

    @classmethod
    def open(cls, path: Path) -> "EpubBook":
        return cls(epub.read_epub(str(path)))

    def chapters(self) -> list[tuple[str, str]]:
        """(title, text) of each chapter: the table of contents, with the documents between two of its entries."""
        return _extract_chapters(self._book)

    @property
    def title(self) -> str | None:
        title = self._book.title
        return title.strip() if title and title.strip() else None

    def cover(self) -> bytes | None:
        """The cover image: an item of type cover, the one of <meta name="cover">, or an image named "cover"."""
        book = self._book
        content = next((item.get_content() for item in book.get_items_of_type(ebooklib.ITEM_COVER)), None)
        if not content:
            cover_meta = book.get_metadata("OPF", "cover")
            item = book.get_item_with_id(cover_meta[0][0]) if cover_meta else None
            content = item.get_content() if item else None
        if not content:
            content = next((item.get_content() for item in book.get_items_of_type(ebooklib.ITEM_IMAGE)
                            if "cover" in item.file_name.lower()), None)
        return content or None
