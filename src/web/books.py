import hashlib
import html
import json
import posixpath
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from lxml import etree
from lxml import html as lxml_html

from gui_components.constants import ROOT

DIR_LIBRARY = ROOT / "library"

# Bump when the rendering changes: books imported with an older version are rendered again on access.
RENDER_VERSION = 1

BOOK_EXTENSIONS = ("epub", "txt", "html", "htm", "xhtml", "md")

# Text files without chapter headings are split into parts of about this many characters,
# so that very long files stay fast to lay out in the browser.
TXT_PART_CHARS = 20_000


class BookError(ValueError):
    pass


# ---------------------------------------------------------------- language detection

_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")
_HAN = re.compile(r"[一-鿿㐀-䶿]")
_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")
# Very frequent characters that only exist in one of the two scripts.
_TRAD_ONLY = set("這們個說國對來時會為們與從學後還麼開關見話讓認經長過現發問進點樣頭邊應實當")
_SIMP_ONLY = set("这们个说国对来时会为们与从学后还么开关见话让认经长过现发问进点样头边应实当")
_LATIN_HINTS = {
    "fr": {" le ", " la ", " les ", " des ", " est ", " une ", " et ", " que ", " pas ", " dans "},
    "es": {" el ", " los ", " las ", " una ", " que ", " y ", " por ", " para ", " está "},
    "it": {" il ", " gli ", " della ", " una ", " che ", " non ", " sono ", " per "},
    "de": {" der ", " die ", " und ", " nicht ", " ist ", " ein ", " eine ", " ich "},
    "pt": {" não ", " uma ", " os ", " que ", " para ", " com ", " está "},
    "pl": {" się ", " nie ", " jest ", " że ", " na ", " i ", " to "},
    "vi": {" của ", " và ", " là ", " không ", " có ", " người "},
    "en": {" the ", " and ", " of ", " to ", " is ", " that ", " was "},
}


# Guesses a BCP-47 language tag from a text sample (used for TXT files, and to fix EPUBs whose
# metadata language is obviously wrong, e.g. a Japanese book tagged "fr" by its authoring tool).
def detect_language(text: str) -> str | None:
    sample = text[:40_000]
    kana, hangul, han = len(_KANA.findall(sample)), len(_HANGUL.findall(sample)), len(_HAN.findall(sample))
    latin = len(_LATIN.findall(sample))
    if kana > 20 and kana >= han * 0.1:
        return "ja"
    if hangul > 20 and hangul >= han:
        return "ko"
    if han > 20 and han > latin:
        trad = sum(1 for ch in sample if ch in _TRAD_ONLY)
        simp = sum(1 for ch in sample if ch in _SIMP_ONLY)
        return "zh-Hans" if simp > trad else "zh-Hant"
    if latin > 50:
        lowered = f" {sample.lower()} "
        scores = {lang: sum(lowered.count(w) for w in words) for lang, words in _LATIN_HINTS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else None
    return None


def _script_family(lang: str | None) -> str:
    lang = (lang or "").lower()
    if lang.startswith(("ja",)):
        return "ja"
    if lang.startswith(("zh", "yue", "cmn")):
        return "zh"
    if lang.startswith("ko"):
        return "ko"
    return "latin" if lang else ""


def _pick_language(declared: str | None, sample: str) -> str:
    detected = detect_language(sample)
    if not declared:
        return detected or "und"
    if detected and _script_family(detected) != _script_family(declared):
        return detected
    if declared.lower() in ("zh", "zh-cn", "zh-sg"):
        return "zh-Hans"
    if declared.lower() in ("zh-tw", "zh-hk", "zh-mo"):
        return "zh-Hant"
    return declared


# ---------------------------------------------------------------- text decoding

_DECODE_CANDIDATES = ("big5", "gb18030", "shift_jis", "euc-kr", "cp1252")


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Legacy CJK encodings: keep the strict decodings and prefer the one that reads as the most
    # "ordinary" text (common CJK, kana, hangul or ASCII), since several of them accept the same bytes.
    best, best_score = None, -1.0
    for encoding in _DECODE_CANDIDATES:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        sample = text[:20_000]
        ordinary = sum(
            1 for ch in sample
            if ch.isascii() or "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ"
            or "가" <= ch <= "힯" or "　" <= ch <= "〿" or "＀" <= ch <= "￯"
        )
        score = ordinary / max(1, len(sample))
        if score > best_score:
            best, best_score = text, score
    return best if best is not None else data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- HTML sanitizing

_KEEP_TAGS = {
    "p", "div", "span", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "em", "strong", "b", "i", "u", "s", "sub", "sup", "small", "big", "mark",
    "ruby", "rb", "rt", "rp", "rtc", "a", "img", "figure", "figcaption", "blockquote",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "section", "article", "aside", "header", "footer", "nav", "main", "pre", "code", "q", "cite",
    "abbr", "wbr", "svg", "image", "g",
}
# Removed with their content.
_DROP_TAGS = {
    "script", "style", "head", "title", "link", "meta", "iframe", "object", "embed", "form",
    "input", "button", "select", "textarea", "audio", "video", "source", "track", "noscript", "canvas",
}
_KEEP_ATTRS = {"id", "href", "src", "alt", "title", "colspan", "rowspan", "width", "height",
               "viewbox", "preserveaspectratio", "lang", "dir", "type"}
_WHITESPACE = re.compile(r"\s+")


def _local(name) -> str:
    if not isinstance(name, str):
        return ""
    return name.rsplit("}", 1)[-1].split(":")[-1].lower()


class _Context:
    """How to rewrite the links and images of one chapter."""

    def __init__(self, book_id: str, chapter_path: str, spine_index: dict[str, int], resources: set[str]):
        self.book_id = book_id
        self.chapter_path = chapter_path  # path of the chapter inside the EPUB ("" for TXT/HTML)
        self.spine_index = spine_index    # EPUB path -> chapter number
        self.resources = resources        # EPUB paths of extracted images

    def resolve(self, ref: str) -> tuple[str, str]:
        parts = urlsplit(ref)
        if not parts.path:
            return self.chapter_path, parts.fragment
        base = posixpath.dirname(self.chapter_path)
        return posixpath.normpath(posixpath.join(base, unquote(parts.path))), parts.fragment

    def image_url(self, ref: str) -> str | None:
        if not ref or ref.startswith(("data:", "http:", "https:")):
            return ref if ref and ref.startswith("data:image/") else None
        path, _ = self.resolve(ref)
        if path not in self.resources:
            return None
        return f"/reader/api/books/{self.book_id}/res/{quote(path)}"

    def link(self, ref: str) -> dict:
        if ref.startswith(("http://", "https://", "mailto:")):
            return {"href": ref, "target": "_blank", "rel": "noopener noreferrer"}
        path, fragment = self.resolve(ref)
        chapter = self.spine_index.get(path)
        if chapter is None:
            return {}
        return {"href": "#", "data-chapter": str(chapter), "data-anchor": f"c-{fragment}" if fragment else ""}


def _sanitize_element(el, ctx: _Context) -> None:
    for child in list(el):
        if not isinstance(child.tag, str):  # comments, processing instructions
            _remove_keep_tail(child)
            continue
        name = _local(child.tag)
        if name in _DROP_TAGS:
            _remove_keep_tail(child)
            continue
        _sanitize_element(child, ctx)
        if name not in _KEEP_TAGS:
            _unwrap(child)
            continue
        child.tag = name
        attrs = {}
        for key, value in child.attrib.items():
            local = _local(key)
            if local == "type" and ("idpf.org/2007/ops" in str(key) or str(key).startswith("epub")):
                attrs["data-epub-type"] = value
            elif local == "lang":
                attrs["lang"] = value
            elif local in _KEEP_ATTRS and local != "type":
                attrs[local] = value
        child.attrib.clear()
        if "id" in attrs:
            attrs["id"] = f"c-{attrs['id']}"
        if name == "a":
            link = ctx.link(attrs.pop("href", "")) if attrs.get("href") else {}
            attrs.update(link)
        elif name == "img":
            url = ctx.image_url(attrs.get("src", ""))
            if url is None:
                _remove_keep_tail(child)
                continue
            attrs["src"] = url
            attrs.setdefault("alt", "")
            attrs["loading"] = "lazy"
        elif name == "image":
            url = ctx.image_url(attrs.pop("href", ""))
            if url is None:
                _remove_keep_tail(child)
                continue
            attrs["href"] = url
        elif name == "svg" and "viewbox" in attrs:
            attrs["viewBox"] = attrs.pop("viewbox")
        if "preserveaspectratio" in attrs:
            attrs["preserveAspectRatio"] = attrs.pop("preserveaspectratio")
        for key, value in attrs.items():
            child.set(key, value)


def _remove_keep_tail(el) -> None:
    parent = el.getparent()
    if parent is None:
        return
    if el.tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def _unwrap(el) -> None:
    parent = el.getparent()
    if parent is None:
        return
    index = parent.index(el)
    prev = el.getprevious()
    text = el.text or ""
    if prev is not None:
        prev.tail = (prev.tail or "") + text
    else:
        parent.text = (parent.text or "") + text
    children = list(el)
    for offset, child in enumerate(children):
        parent.insert(index + offset, child)
    last = children[-1] if children else (parent[index - 1] if index > 0 else None)
    if el.tail:
        if last is not None:
            last.tail = (last.tail or "") + el.tail
        else:
            parent.text = (parent.text or "") + el.tail
    parent.remove(el)


def _parse_document(data: bytes):
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError:
        root = None
    if root is None or not len(root):
        root = lxml_html.document_fromstring(data)
    return root


def _find_body(root):
    for el in root.iter():
        if isinstance(el.tag, str) and _local(el.tag) == "body":
            return el
    return root


# Counts characters the way the reader does: every text node that isn't only whitespace,
# except ruby annotations (<rt>/<rp>), which aren't part of the reading position.
def _in_ruby_text(el) -> bool:
    while el is not None:
        if isinstance(el.tag, str) and _local(el.tag) in ("rt", "rp"):
            return True
        el = el.getparent()
    return False


def count_chars(fragment_root) -> int:
    total = 0
    for el in fragment_root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.text and el.text.strip() and not _in_ruby_text(el):
            total += len(el.text)
        if el is not fragment_root and el.tail and el.tail.strip() and not _in_ruby_text(el.getparent()):
            total += len(el.tail)
    return total


def render_document(data: bytes, ctx: _Context) -> tuple[str, int, str]:
    """Returns (sanitized inner HTML of the body, character count, plain text sample)."""
    root = _parse_document(data)
    body = _find_body(root)
    container = etree.Element("div")
    container.text = body.text
    for child in list(body):
        container.append(child)
    _sanitize_element(container, ctx)
    etree.cleanup_namespaces(container)
    fragment = etree.tostring(container, method="html", encoding="unicode")
    fragment = re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", fragment)
    # strip the wrapping <div>...</div>
    inner = fragment[fragment.index(">") + 1: fragment.rindex("</div>")]
    text = "".join(container.itertext())
    return inner.strip(), count_chars(container), _WHITESPACE.sub(" ", text)[:5000]


# ---------------------------------------------------------------- EPUB

_OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


def _xml(data: bytes):
    return etree.fromstring(data, etree.XMLParser(recover=True, resolve_entities=False, no_network=True))


def _first_text(root, xpath: str) -> str | None:
    found = root.xpath(xpath, namespaces=_OPF_NS)
    for item in found:
        text = (item.text if hasattr(item, "text") else str(item)) or ""
        if text.strip():
            return text.strip()
    return None


def _epub_toc(zf: zipfile.ZipFile, opf_dir: str, manifest: dict, spine_paths: list[str], spine_tag) -> list[dict]:
    spine_index = {p: i for i, p in enumerate(spine_paths)}
    entries: list[dict] = []

    def add(label: str, href: str, base_dir: str, depth: int) -> None:
        parts = urlsplit(href)
        path = posixpath.normpath(posixpath.join(base_dir, unquote(parts.path))) if parts.path else ""
        if path in spine_index and label.strip():
            entries.append({
                "title": _WHITESPACE.sub(" ", label).strip(),
                "chapter": spine_index[path],
                "anchor": f"c-{parts.fragment}" if parts.fragment else "",
                "depth": depth,
            })

    nav = next((item for item in manifest.values() if "nav" in item["properties"]), None)
    if nav is not None:
        try:
            root = _parse_document(zf.read(nav["path"]))
            base = posixpath.dirname(nav["path"])
            for nav_el in root.iter():
                if not isinstance(nav_el.tag, str) or _local(nav_el.tag) != "nav":
                    continue
                types = " ".join(v for k, v in nav_el.attrib.items() if _local(k) == "type")
                if types and "toc" not in types:
                    continue

                def walk(ol, depth):
                    for li in ol:
                        if not isinstance(li.tag, str) or _local(li.tag) != "li":
                            continue
                        for child in li:
                            if isinstance(child.tag, str) and _local(child.tag) == "a":
                                add("".join(child.itertext()), child.get("href", ""), base, depth)
                            elif isinstance(child.tag, str) and _local(child.tag) == "ol":
                                walk(child, depth + 1)

                for ol in nav_el:
                    if isinstance(ol.tag, str) and _local(ol.tag) == "ol":
                        walk(ol, 0)
                break
        except (KeyError, etree.XMLSyntaxError):
            entries = []
    if entries:
        return entries

    ncx_id = spine_tag.get("toc") if spine_tag is not None else None
    ncx = manifest.get(ncx_id) or next((m for m in manifest.values() if m["media_type"] == "application/x-dtbncx+xml"), None)
    if ncx is not None:
        try:
            root = _xml(zf.read(ncx["path"]))
            base = posixpath.dirname(ncx["path"])

            def walk_points(parent, depth):
                for point in parent:
                    if not isinstance(point.tag, str) or _local(point.tag) != "navpoint":
                        continue
                    label = next((el.text for el in point.iter()
                                  if isinstance(el.tag, str) and _local(el.tag) == "text" and el.text), "")
                    content = next((el for el in point if isinstance(el.tag, str) and _local(el.tag) == "content"), None)
                    if content is not None:
                        add(label, content.get("src", ""), base, depth)
                    walk_points(point, depth + 1)

            navmap = next((el for el in root.iter() if isinstance(el.tag, str) and _local(el.tag) == "navmap"), None)
            if navmap is not None:
                walk_points(navmap, 0)
        except (KeyError, etree.XMLSyntaxError):
            pass
    return entries


def _import_epub(source: Path, book_dir: Path, book_id: str) -> dict:
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile:
        raise BookError("This EPUB file is damaged (not a valid zip archive).")
    with zf:
        names = set(zf.namelist())
        try:
            container = _xml(zf.read("META-INF/container.xml"))
        except KeyError:
            raise BookError("This EPUB has no META-INF/container.xml.")
        rootfile = next((el.get("full-path") for el in container.iter() if _local(el.tag) == "rootfile"), None)
        if not rootfile or rootfile not in names:
            raise BookError("Could not find the book's package (OPF) file.")
        if "META-INF/encryption.xml" in names:
            enc = zf.read("META-INF/encryption.xml")
            if b"EncryptedData" in enc and b"obfuscation" not in enc.lower() and b"font" not in enc.lower():
                raise BookError("This EPUB is DRM-protected and can't be opened.")
        opf = _xml(zf.read(rootfile))
        opf_dir = posixpath.dirname(rootfile)

        manifest: dict[str, dict] = {}
        for item in opf.iter():
            if _local(item.tag) == "item" and item.get("id") and item.get("href"):
                path = posixpath.normpath(posixpath.join(opf_dir, unquote(item.get("href"))))
                manifest[item.get("id")] = {
                    "path": path,
                    "media_type": item.get("media-type", ""),
                    "properties": (item.get("properties") or "").split(),
                }
        spine_tag = next((el for el in opf.iter() if _local(el.tag) == "spine"), None)
        spine_paths = []
        if spine_tag is not None:
            for ref in spine_tag:
                if _local(ref.tag) != "itemref":
                    continue
                item = manifest.get(ref.get("idref"))
                if item and item["path"] in names and ref.get("linear", "yes") != "no":
                    spine_paths.append(item["path"])
        if not spine_paths:
            raise BookError("This EPUB has no readable chapters.")

        title = _first_text(opf, "//dc:title") or source.stem
        author = _first_text(opf, "//dc:creator")
        declared_lang = _first_text(opf, "//dc:language")
        progression = spine_tag.get("page-progression-direction") if spine_tag is not None else None
        writing_meta = next((el.get("content") for el in opf.iter()
                             if _local(el.tag) == "meta" and el.get("name") == "primary-writing-mode"), None)

        # images: extracted so they can be served as plain files
        resources = set()
        res_dir = book_dir / "res"
        for item in manifest.values():
            if item["media_type"].startswith("image/") and item["path"] in names:
                target = (res_dir / item["path"]).resolve()
                if not target.is_relative_to(res_dir.resolve()):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(item["path"]))
                resources.add(item["path"])

        cover = next((m["path"] for m in manifest.values() if "cover-image" in m["properties"]), None)
        if cover is None:
            cover_id = next((el.get("content") for el in opf.iter() if _local(el.tag) == "meta" and el.get("name") == "cover"), None)
            if cover_id in manifest:
                cover = manifest[cover_id]["path"]
        if cover not in resources:
            cover = None

        spine_index = {p: i for i, p in enumerate(spine_paths)}
        chapters_dir = book_dir / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        chapters, sample = [], ""
        for i, path in enumerate(spine_paths):
            ctx = _Context(book_id, path, spine_index, resources)
            inner, chars, text = render_document(zf.read(path), ctx)
            (chapters_dir / f"{i:04d}.html").write_text(inner, encoding="utf-8")
            heading = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", inner, re.S)
            chapters.append({"chars": chars, "title": _strip_tags(heading.group(1)) if heading else ""})
            if len(sample) < 20_000:
                sample += text

        toc = _epub_toc(zf, opf_dir, manifest, spine_paths, spine_tag)

    language = _pick_language(declared_lang, sample)
    if writing_meta and "vertical" in writing_meta:
        writing = "vertical"
    elif progression == "rtl" and _script_family(language) in ("ja", "zh"):
        writing = "vertical"
    else:
        writing = "horizontal"
    for i, chapter in enumerate(chapters):
        entry = next((t for t in toc if t["chapter"] == i and t["depth"] == 0), None)
        chapter["title"] = (entry["title"] if entry else chapter["title"]) or f"{i + 1}"
    return {
        "title": title, "author": author, "language": language, "writing": writing,
        "format": "epub", "chapters": chapters, "toc": toc,
        "cover": f"/reader/api/books/{book_id}/res/{quote(cover)}" if cover else None,
    }


def _strip_tags(fragment: str) -> str:
    return html.unescape(_WHITESPACE.sub(" ", re.sub(r"<[^>]+>", "", fragment))).strip()


# ---------------------------------------------------------------- TXT

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


def _import_text(source: Path, book_dir: Path, book_id: str, markdown: bool = False, name: str = "") -> dict:
    text = decode_text(source.read_bytes())
    chapters_dir = book_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapters, toc = [], []
    for i, (heading, lines) in enumerate(split_text_chapters(text)):
        if markdown:
            lines = [re.sub(r"^\s{0,3}#{1,6}\s*", "", l) for l in lines]
        body_lines = lines[1:] if heading else lines
        inner, chars = _paragraphs_html(body_lines)
        if heading:
            inner = f"<h2>{html.escape(heading)}</h2>\n{inner}"
            chars += len(heading)
            toc.append({"title": heading, "chapter": i, "anchor": "", "depth": 0})
        (chapters_dir / f"{i:04d}.html").write_text(inner, encoding="utf-8")
        first_line = next((l.strip() for l in body_lines if l.strip()), "")
        if not heading and i == 0 and len(first_line) <= 40:
            title = first_line  # usually the book's title, before the first chapter heading
        else:
            title = heading or f"Part {i + 1}"
        chapters.append({"chars": chars, "title": title or f"Part {i + 1}"})
    language = detect_language(text) or "und"
    return {
        "title": Path(name).stem or source.stem, "author": None, "language": language,
        "writing": "horizontal", "format": "md" if markdown else "txt",
        "chapters": chapters, "toc": toc, "cover": None,
    }


def _import_html(source: Path, book_dir: Path, book_id: str, name: str = "") -> dict:
    data = source.read_bytes()
    root = _parse_document(data)
    title_el = next((el for el in root.iter() if isinstance(el.tag, str) and _local(el.tag) == "title"), None)
    declared = next((v for el in root.iter() if isinstance(el.tag, str) and _local(el.tag) == "html"
                     for k, v in el.attrib.items() if _local(k) == "lang"), None)
    inner, chars, sample = render_document(data, _Context(book_id, "", {}, set()))
    chapters_dir = book_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "0000.html").write_text(inner, encoding="utf-8")
    title = (title_el.text or "").strip() if title_el is not None else ""
    return {
        "title": title or Path(name).stem or source.stem, "author": None, "language": _pick_language(declared, sample),
        "writing": "horizontal", "format": "html", "chapters": [{"chars": chars, "title": title or "1"}],
        "toc": [], "cover": None,
    }


# ---------------------------------------------------------------- library

_lock = threading.RLock()


def books_dir() -> Path:
    return DIR_LIBRARY / "books"


def _book_dir(book_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", book_id or ""):
        raise BookError("Unknown book.")
    return books_dir() / book_id


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _render(book_dir: Path, book_id: str) -> dict:
    source = next(book_dir.glob("source.*"), None)
    if source is None:
        raise BookError("The book's file is missing from the library.")
    for sub in ("chapters", "res"):
        shutil.rmtree(book_dir / sub, ignore_errors=True)
    ext = source.suffix.lower().lstrip(".")
    old = _read_json(book_dir / "meta.json", {})
    name = old.get("filename", source.name)
    if ext == "epub":
        meta = _import_epub(source, book_dir, book_id)
        if meta["title"] == source.stem:
            meta["title"] = Path(name).stem
    elif ext in ("txt", "md"):
        meta = _import_text(source, book_dir, book_id, markdown=ext == "md", name=name)
    else:
        meta = _import_html(source, book_dir, book_id, name=name)
    meta.update({
        "id": book_id,
        "filename": name,
        "added": old.get("added", time.time()),
        "render_version": RENDER_VERSION,
        "total_chars": sum(c["chars"] for c in meta["chapters"]),
    })
    _write_json(book_dir / "meta.json", meta)
    return meta


def import_book(filename: str, data: bytes) -> dict:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in BOOK_EXTENSIONS:
        raise BookError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(BOOK_EXTENSIONS)})")
    book_id = hashlib.sha256(data).hexdigest()[:16]
    book_dir = _book_dir(book_id)
    with _lock:
        if (book_dir / "meta.json").exists():
            return get_meta(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / f"source.{ext}").write_bytes(data)
        _write_json(book_dir / "meta.json", {"filename": Path(filename).name, "added": time.time()})
        try:
            return _render(book_dir, book_id)
        except Exception:
            shutil.rmtree(book_dir, ignore_errors=True)
            raise


def get_meta(book_id: str) -> dict:
    book_dir = _book_dir(book_id)
    with _lock:
        meta = _read_json(book_dir / "meta.json", None)
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
    return (_book_dir(book_id) / "chapters" / f"{index:04d}.html").read_text(encoding="utf-8")


def resource_path(book_id: str, ref: str) -> Path:
    res_dir = (_book_dir(book_id) / "res").resolve()
    path = (res_dir / ref).resolve()
    if not path.is_relative_to(res_dir) or not path.is_file():
        raise BookError("No such resource.")
    return path


def delete_book(book_id: str) -> None:
    book_dir = _book_dir(book_id)
    with _lock:
        if book_dir.exists():
            shutil.rmtree(book_dir)


def get_progress(book_id: str) -> dict:
    return _read_json(_book_dir(book_id) / "progress.json", {})


def save_progress(book_id: str, chapter, offset, percent) -> dict:
    meta = get_meta(book_id)
    try:
        chapter = max(0, min(int(chapter), len(meta["chapters"]) - 1))
        offset = max(0, int(offset))
        percent = max(0.0, min(100.0, float(percent)))
    except (TypeError, ValueError):
        raise BookError("Invalid position.")
    progress = {"chapter": chapter, "offset": offset, "percent": round(percent, 2), "updated": time.time()}
    _write_json(_book_dir(book_id) / "progress.json", progress)
    return progress


_PREF_KEYS = {"writing": ("auto", "horizontal", "vertical"), "language": None}


def get_prefs(book_id: str) -> dict:
    return _read_json(_book_dir(book_id) / "prefs.json", {})


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
    _write_json(_book_dir(book_id) / "prefs.json", current)
    return current


DEFAULT_SETTINGS = {
    "font_size": 20, "line_height": 1.8, "font": "serif", "theme": "light",
    "margin": 48, "furigana": True,
    # MiningCat's dictionary popup: "click" a word, "shift" + hover like Yomitan, or "off" to use Yomitan.
    "lookup": "click",
    # Words coloured by their status ("status"), or not at all ("off").
    "colors": "status",
    # Recommended (i+1) sentences underlined in the text.
    "i1": True,
}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **_read_json(DIR_LIBRARY / "reader_settings.json", {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif isinstance(default, (int, float)):
            try:
                value = type(default)(value)
            except (TypeError, ValueError):
                continue
            limits = {"font_size": (10, 48), "line_height": (1.1, 3.0), "margin": (0, 160)}[key]
            settings[key] = max(limits[0], min(limits[1], value))
        elif key == "font" and value in ("serif", "sans"):
            settings[key] = value
        elif key == "theme" and value in ("light", "sepia", "dark", "auto"):
            settings[key] = value
        elif key == "lookup" and value in ("click", "shift", "off"):
            settings[key] = value
        elif key == "colors" and value in ("status", "off"):
            settings[key] = value
    _write_json(DIR_LIBRARY / "reader_settings.json", settings)
    return settings
