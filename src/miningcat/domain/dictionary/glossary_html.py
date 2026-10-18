"""A dictionary row's glossary as simple HTML, for the dictionary popup of an e-reader (KOReader shows it with MuPDF):
the page's renderGlossary (mining.js) without what an e-reader can't use, images, colours and links."""
from html import escape

# Yomitan's structured content tags, as they are; the others become a <span>. <a> links to other entries, which the
# e-reader can't follow, and <details> folds what the e-reader shows anyway.
_TAGS = {"br", "ruby", "rt", "rp", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "span", "div", "ol", "ul", "li"}
_BLOCK_TAGS = {"details": "div", "summary": "div"}


def _attributes(node: dict) -> str:
    out = ""
    if isinstance(node.get("lang"), str):
        out += f' lang="{escape(node["lang"])}"'
    for key, name in (("colSpan", "colspan"), ("rowSpan", "rowspan")):
        if isinstance(node.get(key), int):
            out += f' {name}="{node[key]}"'
    return out


def structured_html(node) -> str:
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return escape(str(node))
    if isinstance(node, list):
        return "".join(structured_html(n) for n in node)
    if not isinstance(node, dict) or node.get("tag") == "img":
        return ""
    tag = node.get("tag")
    tag = tag if tag in _TAGS else _BLOCK_TAGS.get(tag, "span")
    if tag == "br":
        return "<br>"
    return f"<{tag}{_attributes(node)}>{structured_html(node.get('content'))}</{tag}>"


def _examples_html(examples: list[dict]) -> str:
    if not examples:
        return ""
    items = "".join(f"<li><i>{escape(x.get('text') or '')}</i>"
                    + (f"<br>{escape(x['translation'])}" if x.get("translation") else "") + "</li>" for x in examples)
    return f"<ul>{items}</ul>"


def _sense_html(sense: dict) -> str:
    """A sense's tags, text, examples and sub-senses (the content of its <li>)."""
    tags = "".join(f"<b>{escape(t)}</b> " for t in sense.get("tags") or [])
    subs = sense.get("subs") or []
    return (tags + escape(sense.get("text") or "") + _examples_html(sense.get("examples") or [])
            + (f"<ol>{''.join(f'<li>{_sense_html(s)}</li>' for s in subs)}</ol>" if subs else ""))


def _numbered(senses: list[str]) -> str:
    """Numbered senses; a single one without its number."""
    if len(senses) == 1:
        return f"<div>{senses[0]}</div>"
    return "<ol>" + "".join(f"<li>{s}</li>" for s in senses) + "</ol>"


def _senses_html(item: dict) -> str:
    """Numbered senses, each pronunciation's in its own list."""
    out, senses = "", []
    for sense in item.get("senses") or []:
        if sense.get("reading"):
            if senses:
                out += _numbered(senses)
                senses = []
            out += f"<p><b>{escape(sense['reading'])}</b></p>"
        else:
            senses.append(_sense_html(sense))
    if senses:
        out += _numbered(senses)
    return out + _examples_html(item.get("examples") or [])


def glossary_html(glossary: list) -> str:
    parts = []
    for item in glossary:
        if isinstance(item, str):
            parts.append(escape(item).replace("\n", "<br>"))
        elif isinstance(item, list) and item:
            parts.append(f"→ {escape(str(item[0]))}")  # a deinflection rule: "→ 食べる"
        elif isinstance(item, dict) and item.get("type") == "senses":
            parts.append(_senses_html(item))
        elif isinstance(item, dict) and item.get("type") == "text":
            parts.append(escape(item.get("text") or "").replace("\n", "<br>"))
        elif isinstance(item, dict) and item.get("type") == "structured-content":
            parts.append(structured_html(item.get("content")))
    if len(parts) == 1:
        return f"<div>{parts[0]}</div>"
    return "<ul>" + "".join(f"<li>{p}</li>" for p in parts) + "</ul>"
