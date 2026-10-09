"""The sentence of a card, with the readings of its words in brackets: 你[ni3]<b>好[hao3]</b>."""
import html
import re

from miningcat.domain.text.zhuyin import numbered_pinyin, pinyin_to_zhuyin, zhuyin_to_pinyin

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


def plain_sentence(sentence_html: str) -> tuple[str, tuple[int, int] | None]:
    """Text of a card's sentence (HTML) and where its bold part, the card's word, is."""
    parts: list[str] = []
    length, pos = 0, 0
    bold_start = bold_end = None
    for m in _TAG.finditer(sentence_html):
        chunk = html.unescape(sentence_html[pos:m.start()])
        parts.append(chunk)
        length += len(chunk)
        pos = m.end()
        name = m.group(2).lower()
        if name in ("b", "strong"):
            if not m.group(1) and bold_start is None:
                bold_start = length
            elif m.group(1) and bold_start is not None and bold_end is None:
                bold_end = length
        elif name == "br":
            parts.append("\n")
            length += 1
    parts.append(html.unescape(sentence_html[pos:]))
    text = "".join(parts).replace("\xa0", " ")
    if bold_start is None:
        return text, None
    bold_end = len(text) if bold_end is None else bold_end
    return text, (bold_start, bold_end) if bold_end > bold_start else None


def display_pinyin(pinyin: str, system: str) -> str:
    zhuyin = pinyin_to_zhuyin(pinyin)
    return zhuyin if system == "zhuyin" else zhuyin_to_pinyin(zhuyin) or pinyin


def _escape(text: str) -> str:
    return html.escape(text, quote=False).replace("\n", "<br>")


def bracketed(text: str, tokens: list[dict]) -> str:
    """The sentence with each word's reading in brackets after it, the card's word in bold: 你[ni3]<b>好[hao3]</b>."""
    out: list[str] = []
    pos = 0
    for token in tokens:
        out.append(_escape(text[pos:token["start"]]))
        word = _escape(token["text"]) + (f"[{token['pinyin']}]" if token.get("pinyin") else "")
        out.append(f"<b>{word}</b>" if token.get("target") else word)
        pos = token["end"]
    out.append(_escape(text[pos:]))
    return "".join(out)


def word_field(word: str, reading: str) -> str:
    """The card's word with its reading in brackets: 繁體字[fan2 ti3 zi4]."""
    pinyin = numbered_pinyin(reading)
    return f"{word}[{pinyin}]" if word and pinyin else word
