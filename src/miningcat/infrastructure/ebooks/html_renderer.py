"""Chapters of ebooks rendered to clean HTML fragments: the publisher's scripts, styles and unknown tags are
dropped, links and images rewritten for the reader."""
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit

from lxml import etree
from lxml import html as lxml_html

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

WHITESPACE = re.compile(r"\s+")


def local_name(name) -> str:
    if not isinstance(name, str):
        return ""
    return name.rsplit("}", 1)[-1].split(":")[-1].lower()


class RenderContext:
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


def _sanitize_element(el, ctx: RenderContext) -> None:
    for child in list(el):
        if not isinstance(child.tag, str):  # comments, processing instructions
            _remove_keep_tail(child)
            continue
        name = local_name(child.tag)
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
            local = local_name(key)
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


def parse_document(data: bytes):
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
        if isinstance(el.tag, str) and local_name(el.tag) == "body":
            return el
    return root


# Counts characters the way the reader does: every text node that isn't only whitespace,
# except ruby annotations (<rt>/<rp>), which aren't part of the reading position.
def _in_ruby_text(el) -> bool:
    while el is not None:
        if isinstance(el.tag, str) and local_name(el.tag) in ("rt", "rp"):
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


def render_document(data: bytes, ctx: RenderContext) -> tuple[str, int, str]:
    """Returns (sanitized inner HTML of the body, character count, plain text sample)."""
    root = parse_document(data)
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
    return inner.strip(), count_chars(container), WHITESPACE.sub(" ", text)[:5000]
