"""The package of an EPUB (zip): its OPF manifest, reading order, metadata and table of contents."""
import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree

from miningcat.domain.library.errors import BookError
from miningcat.infrastructure.ebooks.html_renderer import WHITESPACE, local_name, parse_document

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


def read_toc(zf: zipfile.ZipFile, opf_dir: str, manifest: dict, spine_paths: list[str], spine_tag) -> list[dict]:
    spine_index = {p: i for i, p in enumerate(spine_paths)}
    entries: list[dict] = []

    def add(label: str, href: str, base_dir: str, depth: int) -> None:
        parts = urlsplit(href)
        path = posixpath.normpath(posixpath.join(base_dir, unquote(parts.path))) if parts.path else ""
        if path in spine_index and label.strip():
            entries.append({
                "title": WHITESPACE.sub(" ", label).strip(),
                "chapter": spine_index[path],
                "anchor": f"c-{parts.fragment}" if parts.fragment else "",
                "depth": depth,
            })

    nav = next((item for item in manifest.values() if "nav" in item["properties"]), None)
    if nav is not None:
        try:
            root = parse_document(zf.read(nav["path"]))
            base = posixpath.dirname(nav["path"])
            for nav_el in root.iter():
                if not isinstance(nav_el.tag, str) or local_name(nav_el.tag) != "nav":
                    continue
                types = " ".join(v for k, v in nav_el.attrib.items() if local_name(k) == "type")
                if types and "toc" not in types:
                    continue

                def walk(ol, depth):
                    for li in ol:
                        if not isinstance(li.tag, str) or local_name(li.tag) != "li":
                            continue
                        for child in li:
                            if isinstance(child.tag, str) and local_name(child.tag) == "a":
                                add("".join(child.itertext()), child.get("href", ""), base, depth)
                            elif isinstance(child.tag, str) and local_name(child.tag) == "ol":
                                walk(child, depth + 1)

                for ol in nav_el:
                    if isinstance(ol.tag, str) and local_name(ol.tag) == "ol":
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
                    if not isinstance(point.tag, str) or local_name(point.tag) != "navpoint":
                        continue
                    label = next((el.text for el in point.iter()
                                  if isinstance(el.tag, str) and local_name(el.tag) == "text" and el.text), "")
                    content = next((el for el in point if isinstance(el.tag, str) and local_name(el.tag) == "content"), None)
                    if content is not None:
                        add(label, content.get("src", ""), base, depth)
                    walk_points(point, depth + 1)

            navmap = next((el for el in root.iter() if isinstance(el.tag, str) and local_name(el.tag) == "navmap"), None)
            if navmap is not None:
                walk_points(navmap, 0)
        except (KeyError, etree.XMLSyntaxError):
            pass
    return entries


class EpubPackage:
    """An EPUB opened for import: refuses damaged, DRM-protected and empty books."""

    def __init__(self, zf: zipfile.ZipFile, rootfile: str):
        self._zf = zf
        self.names = set(zf.namelist())
        self.opf = _xml(zf.read(rootfile))
        self.opf_dir = posixpath.dirname(rootfile)
        self.manifest: dict[str, dict] = {}
        for item in self.opf.iter():
            if local_name(item.tag) == "item" and item.get("id") and item.get("href"):
                path = posixpath.normpath(posixpath.join(self.opf_dir, unquote(item.get("href"))))
                self.manifest[item.get("id")] = {
                    "path": path,
                    "media_type": item.get("media-type", ""),
                    "properties": (item.get("properties") or "").split(),
                }
        self.spine_tag = next((el for el in self.opf.iter() if local_name(el.tag) == "spine"), None)
        self.spine_paths: list[str] = []
        if self.spine_tag is not None:
            for ref in self.spine_tag:
                if local_name(ref.tag) != "itemref":
                    continue
                item = self.manifest.get(ref.get("idref"))
                if item and item["path"] in self.names and ref.get("linear", "yes") != "no":
                    self.spine_paths.append(item["path"])
        if not self.spine_paths:
            raise BookError("This EPUB has no readable chapters.")

    @classmethod
    def open(cls, path: Path) -> "EpubPackage":
        try:
            zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile:
            raise BookError("This EPUB file is damaged (not a valid zip archive).")
        try:
            names = set(zf.namelist())
            try:
                container = _xml(zf.read("META-INF/container.xml"))
            except KeyError:
                raise BookError("This EPUB has no META-INF/container.xml.")
            rootfile = next((el.get("full-path") for el in container.iter() if local_name(el.tag) == "rootfile"), None)
            if not rootfile or rootfile not in names:
                raise BookError("Could not find the book's package (OPF) file.")
            if "META-INF/encryption.xml" in names:
                enc = zf.read("META-INF/encryption.xml")
                if b"EncryptedData" in enc and b"obfuscation" not in enc.lower() and b"font" not in enc.lower():
                    raise BookError("This EPUB is DRM-protected and can't be opened.")
            return cls(zf, rootfile)
        except Exception:
            zf.close()
            raise

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "EpubPackage":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def read(self, path: str) -> bytes:
        return self._zf.read(path)

    def metadata(self, xpath: str) -> str | None:
        """The first text of a metadata element (//dc:title, //dc:creator...)."""
        return _first_text(self.opf, xpath)

    @property
    def page_progression(self) -> str | None:
        return self.spine_tag.get("page-progression-direction") if self.spine_tag is not None else None

    @property
    def writing_mode(self) -> str | None:
        return next((el.get("content") for el in self.opf.iter()
                     if local_name(el.tag) == "meta" and el.get("name") == "primary-writing-mode"), None)

    def images(self) -> list[str]:
        return [item["path"] for item in self.manifest.values()
                if item["media_type"].startswith("image/") and item["path"] in self.names]

    def cover(self) -> str | None:
        """The path of the cover image: the item with the cover-image property, or the one of <meta name="cover">."""
        cover = next((m["path"] for m in self.manifest.values() if "cover-image" in m["properties"]), None)
        if cover is None:
            cover_id = next((el.get("content") for el in self.opf.iter()
                             if local_name(el.tag) == "meta" and el.get("name") == "cover"), None)
            if cover_id in self.manifest:
                cover = self.manifest[cover_id]["path"]
        return cover

    def toc(self) -> list[dict]:
        """{"title", "chapter", "anchor", "depth"} of each entry of the EPUB 3 nav, else of the EPUB 2 NCX."""
        return read_toc(self._zf, self.opf_dir, self.manifest, self.spine_paths, self.spine_tag)
