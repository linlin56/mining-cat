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


def _text(node) -> str:
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, list):
        return "".join(_text(n) for n in node)
    if isinstance(node, dict):
        return _text(node.get("content"))
    return ""


def _without_headword(node, expression: str):
    """Structured content without its "【除非】" line: the popup already shows the word. A different headword
    (the simplified form 这 of 這) is kept."""
    if isinstance(node, list):
        return [_without_headword(n, expression) for n in node
                if not (isinstance(n, dict) and _text(n).strip() == f"【{expression}】")]
    if isinstance(node, dict) and "content" in node:
        return {**node, "content": _without_headword(node["content"], expression)}
    return node


# comparing meanings

def meaning_keys(text: str) -> set[str]:
    """Keys of the meanings of a gloss, for finding the ones another dictionary already gave: "to walk; to go" ->
    {"walk", "go"}, and "only if (..., or otherwise, ...)" is the "only if" of another dictionary."""
    keys = set()
    for part in re.split(r"[;；]", text.casefold()):
        part = re.sub(r"\([^)]*\)|（[^）]*）", " ", part)
        part = re.sub(r"^\s*to\s+", "", part)
        key = " ".join(re.findall(r"\w+", part))
        if key:
            keys.add(key)
    return keys


def item_meaning_keys(item) -> set[str]:
    """The meanings given by a glossary item: a short text, the list items of structured content, the senses."""
    if isinstance(item, str):
        return meaning_keys(item) if len(item) < 120 else set()
    if not isinstance(item, dict):
        return set()
    if item.get("type") == "text":
        return item_meaning_keys(str(item.get("text", "")))
    if item.get("type") == "senses":
        return {k for s in item["senses"] for k in _sense_keys(s)}
    if item.get("type") == "structured-content":
        keys: set[str] = set()
        _list_item_keys(item.get("content"), keys)
        return keys
    return set()


def _list_item_keys(node, keys: set[str]) -> None:
    if isinstance(node, list):
        for n in node:
            _list_item_keys(n, keys)
    elif isinstance(node, dict):
        if node.get("tag") == "li":
            keys.update(meaning_keys(_text(node)))
        else:
            _list_item_keys(node.get("content"), keys)


def _sense_keys(sense: dict) -> set[str]:
    keys = meaning_keys(sense.get("text", ""))
    for sub in sense.get("subs", ()):
        keys |= _sense_keys(sub)
    return keys


def new_senses(item: dict, seen: set[str]) -> dict | None:
    """`item` without the senses whose meanings are all in `seen` (given by a dictionary shown before, or earlier in
    this one), adding the meanings of the others to `seen`. A sense with examples or sub-senses is kept. None when
    nothing is left."""
    kept = []
    for sense in item["senses"]:
        if "reading" in sense:
            kept.append(sense)
            continue
        keys = meaning_keys(sense["text"])
        if keys and keys <= seen and not sense["examples"] and not sense["subs"]:
            continue
        seen |= keys
        kept.append(sense)
    # a pronunciation none of whose senses is left
    kept = [s for i, s in enumerate(kept)
            if "reading" not in s or (i + 1 < len(kept) and "reading" not in kept[i + 1])]
    if not any("text" in s for s in kept) and not item["examples"]:
        return None
    return {**item, "senses": kept}
