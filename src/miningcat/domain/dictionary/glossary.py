import re

_HEADER = re.compile(r"^\s*【[^】\n]*】\s*(?:\[\d+\]\s*)?")
_NUMBER = re.compile(r"^\d{1,3}\s*[。.．、](?!\d)\s*")
_SUB_NUMBER = re.compile(r"^[(（]\d{1,3}[)）]\s*")
_EXAMPLE_LINE = re.compile(r"^例\s*[:：]\s*")
_INLINE_EXAMPLES = re.compile(r"\s*\[例\]\s*")
_EXAMPLE_SEPARATOR = re.compile(r"\s*[︱│∣｜|]\s*")
_TONE_MARK = re.compile(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]")
_READING_LINE = re.compile(r"^[a-zA-Züāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜɡ' ]{1,30}$")
# A part of speech or register written before a sense: "連詞。", "〈書〉", and the 兩岸詞典 marks of Taiwan (▲) and
# mainland China (★) usage.
_PART_OF_SPEECH = re.compile(r"^(名詞|動詞|形容詞|副詞|連詞|介詞|量詞|助詞|嘆詞|歎詞|代詞|數詞|助動詞|擬聲詞)[。：:]\s*")
_REGISTER = re.compile(r"^〈([^〉]{1,4})〉\s*")
_REGION_MARKS = {"▲": "Taiwan", "★": "Mainland"}


def looks_structured(text: str) -> bool:
    return bool("\n" in text.strip() or _HEADER.match(text) or _NUMBER.match(text.strip()) or "[例]" in text
                or _EXAMPLE_LINE.search(text))


def _is_reading(line: str) -> bool:
    return bool(_READING_LINE.match(line) and _TONE_MARK.search(line))


def _examples(text: str, expression: str) -> list[dict]:
    """[例]美～│完～│花～月圓。 -> 美好, 完好, 花好月圓: the ～ stands for the word."""
    return [{"text": e.replace("～", expression)} for e in _EXAMPLE_SEPARATOR.split(text.strip().rstrip("。"))
            if e.strip()]


def _sense(text: str, expression: str) -> dict:
    tags = []
    while True:
        text = text.strip()
        if text[:1] in _REGION_MARKS:
            tags.append(_REGION_MARKS[text[0]])
            text = text[1:]
        elif m := _PART_OF_SPEECH.match(text) or _REGISTER.match(text):
            tags.append(m.group(1))
            text = text[m.end():]
        else:
            break
    text, *parts = _INLINE_EXAMPLES.split(text)
    return {"text": text.strip(), "tags": tags, "examples": [e for p in parts for e in _examples(p, expression)],
            "subs": []}


def split_senses(text: str, expression: str) -> dict | None:
    """The senses of a definition written as one text, or None when it's a plain gloss ("to walk")."""
    if not looks_structured(text):
        return None
    text = _HEADER.sub("", text, count=1)
    senses: list[dict] = []
    examples: list[dict] = []
    last = None  # the sense or example a continuation line belongs to
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if m := _EXAMPLE_LINE.match(line):
            last = {"text": line[m.end():].strip()}
            examples.append(last)
        elif _is_reading(line):
            senses.append({"reading": line.replace("ɡ", "g")})
            last = None
        elif m := _SUB_NUMBER.match(line):
            last = _sense(line[m.end():], expression)
            parent = next((s for s in reversed(senses) if "text" in s), None)
            (parent["subs"] if parent else senses).append(last)
        elif m := _NUMBER.match(line):
            last = _sense(line[m.end():], expression)
            senses.append(last)
        elif last is not None and "translation" not in last and "tags" not in last:
            last["translation"] = line  # the line under an example translates it
        else:
            last = _sense(line, expression)
            senses.append(last)
    return {"type": "senses", "senses": senses, "examples": examples}


def structure(glossary: list, expression: str) -> list:
    """The glossary of a dictionary row, its block texts split into senses."""
    out = []
    for item in glossary:
        if isinstance(item, str):
            item = split_senses(item, expression) or item
        elif isinstance(item, dict) and item.get("type") == "structured-content":
            item = {**item, "content": _without_headword(item.get("content"), expression)}
        out.append(item)
    return out


def node_text(node) -> str:
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, list):
        return "".join(node_text(n) for n in node)
    if isinstance(node, dict):
        return node_text(node.get("content"))
    return ""


def _without_headword(node, expression: str):
    """Structured content without its "【除非】" line: the popup already shows the word. A different headword
    (the simplified form 这 of 這) is kept."""
    if isinstance(node, list):
        return [_without_headword(n, expression) for n in node
                if not (isinstance(n, dict) and node_text(n).strip() == f"【{expression}】")]
    if isinstance(node, dict) and "content" in node:
        return {**node, "content": _without_headword(node["content"], expression)}
    return node
