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


def sentence_around(before: str, word: str, after: str) -> str:
    """The sentence (or sentences) holding `word`, from the text around it: what an e-reader gives of a word looked up."""
    text = before + word + after
    start, end = len(before), len(before) + max(len(word), 1)
    spans = [(a, b) for a, b in sentence_spans(text) if a < end and b > start]
    if not spans:
        return word.strip()
    return text[spans[0][0]:spans[-1][1]]


def _add_span(spans: list, text: str, start: int, end: int) -> None:
    piece = text[start:end]
    stripped = piece.strip()
    if stripped:
        start += len(piece) - len(piece.lstrip())
        spans.append((start, start + len(stripped)))


# A sentence end (a period only before a space or the end: 3.5 isn't one), then its closing quotes or brackets.
_SPLIT_END = re.compile(r"(?:[。？！?!…]+|\.(?=[\s」』”’\"')）]|$))[」』”’\"')）]*")
_CLAUSE = re.compile(r"[^，,、；;：:]*(?:[，,、；;：:]+|$)")


def split_sentences(text: str, max_chars: int = 80) -> list[str]:
    """The sentences of a text, for engines working sentence by sentence (speech alignment and synthesis): cut after
    the sentence-final punctuation and at line breaks, and a sentence longer than max_chars after its commas."""
    sentences = []
    for line in text.splitlines():
        ends = [m.end() for m in _SPLIT_END.finditer(line)]
        for start, end in zip([0, *ends], [*ends, len(line)]):
            sentence = line[start:end].strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                sentences.append(sentence)
                continue
            part = ""
            for clause in _CLAUSE.findall(sentence):
                if part and len(part) + len(clause) > max_chars:
                    sentences.append(part.strip())
                    part = ""
                part += clause
            if part.strip():
                sentences.append(part.strip())
    return sentences
