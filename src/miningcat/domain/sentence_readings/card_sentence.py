"""The sentence of a card, with the readings of its words in brackets: 你[ni3]<b>好[hao3]</b>."""
import html
import re

from miningcat.domain.text.zhuyin import numbered_pinyin, pinyin_to_zhuyin, zhuyin_to_pinyin

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
_HAN = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f〇"
_HAN_RUNS = re.compile(f"[{_HAN}]+|[^{_HAN}]+")
_HAN_CHAR = re.compile(f"[{_HAN}]")


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


def han_readings(text: str, pinyin: str) -> list[tuple[str, str]]:
    """The parts of a word with their readings: only its Chinese characters are read (the readings of a word's
    letters and digits, A[a5], aren't readings). AA制 read "a5 a5 zhi4" or "zhi4": [("AA", ""), ("制", "zhi4")].
    A word without characters, or whose readings can't be matched to them, has none: [(text, "")]."""
    runs = _HAN_RUNS.findall(text)
    han = [run for run in runs if _HAN_CHAR.match(run)]
    syllables = pinyin.split()
    count = sum(map(len, han))
    if not han or not syllables:
        return [(text, "")]
    if len(syllables) == len(text) and count != len(text):  # a syllable for each letter too: those of the characters
        syllables = [syl for ch, syl in zip(text, syllables) if _HAN_CHAR.match(ch)]
    if len(runs) == 1:
        return [(text, pinyin)]
    if len(syllables) != count:
        return [(text, "")]
    parts = []
    for run in runs:
        if _HAN_CHAR.match(run):
            parts.append((run, " ".join(syllables[:len(run)])))
            syllables = syllables[len(run):]
        else:
            parts.append((run, ""))
    return parts


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
    """The card's word with its reading in brackets: 繁體字[fan2 ti3 zi4], AA制 -> AA制[zhi4], A -> A."""
    return "".join(f"{part}[{pinyin}]" if pinyin else part for part, pinyin in han_readings(word, numbered_pinyin(reading)))
