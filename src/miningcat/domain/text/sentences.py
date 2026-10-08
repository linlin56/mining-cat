import re

# A sentence ends at a line break, or at final punctuation followed by its closing quotes or brackets.
_SENTENCE_END = re.compile(r"(?:[。！？!?…]+|\.+(?=\s|$))[」』）)】〉》”’\"']*|\n")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence of `text`, surrounding spaces excluded."""
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        _add_span(spans, text, start, m.end())
        start = m.end()
    _add_span(spans, text, start, len(text))
    return spans


def _add_span(spans: list, text: str, start: int, end: int) -> None:
    piece = text[start:end]
    stripped = piece.strip()
    if stripped:
        start += len(piece) - len(piece.lstrip())
        spans.append((start, start + len(stripped)))
