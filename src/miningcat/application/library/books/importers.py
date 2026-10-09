"""Books imported into the library: each chapter rendered once to an HTML fragment (chapters/0000.html...), with the
book's metadata. One BookImporter per format."""
import html
import re
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote

from miningcat.domain.library.errors import BookError
from miningcat.domain.text.decoding import decode_text
from miningcat.domain.text.language_detection import detect_language, pick_language, script_family
from miningcat.infrastructure.ebooks.epub_package import EpubPackage
from miningcat.infrastructure.ebooks.html_renderer import (
    WHITESPACE,
    RenderContext,
    local_name,
    parse_document,
    render_document,
)

# Text files without chapter headings are split into parts of about this many characters,
# so that very long files stay fast to lay out in the browser.
TXT_PART_CHARS = 20_000

# A line that starts a chapter: 第一章, 序章, 제1장, Chapter 3, Prologue...
_HEADING = re.compile(
    r"^\s*("
    r"第\s*[0-9０-９一二三四五六七八九十百千零〇两兩]+\s*[章回节節卷部篇话話幕]"
    r"|(?:序章|序言|楔子|引子|尾聲|尾声|終章|终章|後記|后记|番外|あとがき|まえがき|プロローグ|エピローグ)"
    r"|제\s*\d+\s*[장화부]"
    r"|(?:chapter|chapitre|capítulo|capitolo|kapitel|rozdział|chương)\s+[\w.]+"
    r"|(?:prologue|epilogue|prologo|prólogo|épilogue)\b"
    r")[^\n]{0,40}$",
    re.IGNORECASE,
)


def _strip_tags(fragment: str) -> str:
    return html.unescape(WHITESPACE.sub(" ", re.sub(r"<[^>]+>", "", fragment))).strip()


def _write_chapter(book_dir: Path, index: int, inner: str) -> None:
    chapters_dir = book_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / f"{index:04d}.html").write_text(inner, encoding="utf-8")


def _paragraphs_html(lines: list[str]) -> tuple[str, int]:
    parts, chars = [], 0
    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        chars += len(stripped)
        parts.append(f"<p>{html.escape(stripped)}</p>")
    return "\n".join(parts), chars


def split_text_chapters(text: str) -> list[tuple[str, list[str]]]:
    """(heading, lines) of the chapters of a text: at its headings, or parts of about TXT_PART_CHARS without any."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings = [i for i, line in enumerate(lines) if len(line.strip()) <= 50 and _HEADING.match(line)]
    if len(headings) >= 2:
        chapters = []
        if any(l.strip() for l in lines[:headings[0]]):
            chapters.append(("", lines[:headings[0]]))
        for n, start in enumerate(headings):
            end = headings[n + 1] if n + 1 < len(headings) else len(lines)
            chapters.append((lines[start].strip(), lines[start:end]))
        return chapters
    # No headings: split into parts at paragraph boundaries.
    chapters, current, size = [], [], 0
    for line in lines:
        current.append(line)
        size += len(line)
        if size >= TXT_PART_CHARS and not line.strip() or size >= TXT_PART_CHARS * 1.5:
            chapters.append(("", current))
            current, size = [], 0
    if any(l.strip() for l in current) or not chapters:
        chapters.append(("", current))
    return chapters


class BookImporter(ABC):
    """Renders a book file into a book folder of the library. Returns its metadata: title, author, language,
    writing (horizontal or vertical), format, chapters [{chars, title}], toc [{title, chapter, anchor, depth}], cover."""

    @abstractmethod
    def import_book(self, source: Path, book_dir: Path, book_id: str, name: str) -> dict:
        """`name`: the file's original name."""


class EpubImporter(BookImporter):
    def import_book(self, source: Path, book_dir: Path, book_id: str, name: str) -> dict:
        with EpubPackage.open(source) as package:
            resources = self._extract_images(package, book_dir / "res")
            cover = package.cover()
            if cover not in resources:
                cover = None
            spine_index = {p: i for i, p in enumerate(package.spine_paths)}
            chapters, sample = [], ""
            for i, path in enumerate(package.spine_paths):
                inner, chars, text = render_document(package.read(path), RenderContext(book_id, path, spine_index, resources))
                _write_chapter(book_dir, i, inner)
                heading = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", inner, re.S)
                chapters.append({"chars": chars, "title": _strip_tags(heading.group(1)) if heading else ""})
                if len(sample) < 20_000:
                    sample += text
            toc = package.toc()
            title = package.metadata("//dc:title")
            author = package.metadata("//dc:creator")
            declared_lang = package.metadata("//dc:language")
            progression, writing_meta = package.page_progression, package.writing_mode

        language = pick_language(declared_lang, sample)
        if writing_meta and "vertical" in writing_meta:
            writing = "vertical"
        elif progression == "rtl" and script_family(language) in ("ja", "zh"):
            writing = "vertical"
        else:
            writing = "horizontal"
        for i, chapter in enumerate(chapters):
            entry = next((t for t in toc if t["chapter"] == i and t["depth"] == 0), None)
            chapter["title"] = (entry["title"] if entry else chapter["title"]) or f"{i + 1}"
        return {
            "title": title or source.stem, "author": author, "language": language, "writing": writing,
            "format": "epub", "chapters": chapters, "toc": toc,
            "cover": f"/reader/api/books/{book_id}/res/{quote(cover)}" if cover else None,
        }

    @staticmethod
    def _extract_images(package: EpubPackage, res_dir: Path) -> set[str]:
        """The book's images, extracted so they can be served as plain files."""
        resources = set()
        for path in package.images():
            target = (res_dir / path).resolve()
            if not target.is_relative_to(res_dir.resolve()):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(path))
            resources.add(path)
        return resources


class TextImporter(BookImporter):
    """A plain text (or Markdown) file, split at its chapter headings."""

    def __init__(self, markdown: bool = False):
        self.markdown = markdown

    def import_book(self, source: Path, book_dir: Path, book_id: str, name: str) -> dict:
        text = decode_text(source.read_bytes())
        chapters, toc = [], []
        for i, (heading, lines) in enumerate(split_text_chapters(text)):
            if self.markdown:
                lines = [re.sub(r"^\s{0,3}#{1,6}\s*", "", l) for l in lines]
            body_lines = lines[1:] if heading else lines
            inner, chars = _paragraphs_html(body_lines)
            if heading:
                inner = f"<h2>{html.escape(heading)}</h2>\n{inner}"
                chars += len(heading)
                toc.append({"title": heading, "chapter": i, "anchor": "", "depth": 0})
            _write_chapter(book_dir, i, inner)
            first_line = next((l.strip() for l in body_lines if l.strip()), "")
            if not heading and i == 0 and len(first_line) <= 40:
                title = first_line  # usually the book's title, before the first chapter heading
            else:
                title = heading or f"Part {i + 1}"
            chapters.append({"chars": chars, "title": title or f"Part {i + 1}"})
        return {
            "title": Path(name).stem or source.stem, "author": None, "language": detect_language(text) or "und",
            "writing": "horizontal", "format": "md" if self.markdown else "txt",
            "chapters": chapters, "toc": toc, "cover": None,
        }


class HtmlImporter(BookImporter):
    """A single HTML page: one chapter."""

    def import_book(self, source: Path, book_dir: Path, book_id: str, name: str) -> dict:
        data = source.read_bytes()
        root = parse_document(data)
        title_el = next((el for el in root.iter() if isinstance(el.tag, str) and local_name(el.tag) == "title"), None)
        declared = next((v for el in root.iter() if isinstance(el.tag, str) and local_name(el.tag) == "html"
                         for k, v in el.attrib.items() if local_name(k) == "lang"), None)
        inner, chars, sample = render_document(data, RenderContext(book_id, "", {}, set()))
        _write_chapter(book_dir, 0, inner)
        title = (title_el.text or "").strip() if title_el is not None else ""
        return {
            "title": title or Path(name).stem or source.stem, "author": None,
            "language": pick_language(declared, sample), "writing": "horizontal", "format": "html",
            "chapters": [{"chars": chars, "title": title or "1"}], "toc": [], "cover": None,
        }


def importer_for(extension: str) -> BookImporter:
    if extension == "epub":
        return EpubImporter()
    if extension in ("txt", "md"):
        return TextImporter(markdown=extension == "md")
    if extension in ("html", "htm", "xhtml"):
        return HtmlImporter()
    raise BookError(f"Unsupported format: .{extension or '?'}")
