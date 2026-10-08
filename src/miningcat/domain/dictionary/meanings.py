"""Comparing the meanings of glosses, to find the ones another dictionary already gave."""
import re

from miningcat.domain.dictionary.glossary import node_text


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
            keys.update(meaning_keys(node_text(node)))
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
