"""Merging the definitions of several dictionaries into the entries of a lookup."""
import json
import re

from miningcat.domain.dictionary.meanings import item_meaning_keys, new_senses
from miningcat.domain.text.readings import reading_key


# Whether reading `a` should be shown rather than `b` for the same pronunciation: tone marks (xíng) over numbers (xing2).
def readable(a: str, b: str) -> bool:
    return bool(re.search(r"\d", b)) and not re.search(r"\d", a)


def _gloss_key(item) -> str:
    if isinstance(item, str):
        return " ".join(item.casefold().split())
    if isinstance(item, dict) and item.get("type") == "text":
        return " ".join(str(item.get("text", "")).casefold().split())
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def merge_definitions(definitions: list[dict]) -> list[dict]:
    """The definitions of one entry without repeats: rows of a dictionary with the same tags become one sense
    (行 xíng: "walk, OK" and "walk, go" -> "walk, OK, go"), and a gloss already given (by this dictionary or one shown
    before it) isn't repeated, nor a sense of a block text whose meanings were all given ("only if" after CC-CEDICT's
    "only if (..., or otherwise, ...)"). Senses tagged differently (JMdict's numbered senses, parts of speech) stay apart."""
    merged: list[dict] = []
    by_tags: dict[tuple, dict] = {}
    seen: set[str] = set()
    meanings: set[str] = set()
    for definition in definitions:
        glossary = definition["glossary"] if isinstance(definition["glossary"], list) else [definition["glossary"]]
        fresh = []
        for item in glossary:
            if isinstance(item, dict) and item.get("type") == "senses":
                item = new_senses(item, meanings)
                if item:
                    fresh.append(item)
                continue
            key = _gloss_key(item)
            if key and key not in seen:
                seen.add(key)
                meanings |= item_meaning_keys(item)
                fresh.append(item)
        if not fresh:
            continue
        same = (definition["dict_id"], tuple(definition["tags"]), tuple(definition["term_tags"]))
        if same in by_tags:
            by_tags[same]["glossary"].extend(fresh)
        else:
            definition = {**definition, "glossary": fresh}
            by_tags[same] = definition
            merged.append(definition)
    return merged


def move_other_readings(groups: dict[tuple, dict], language: str) -> None:
    """The senses a block text gives for another pronunciation (DrEye's 好 hǎo: "…8。easily\nhào\n9。to be fond of")
    go to the entry of that pronunciation when there is one."""
    for (expression, key), group in list(groups.items()):
        for definition in group["definitions"]:
            for i, item in enumerate(definition["glossary"]):
                if not (isinstance(item, dict) and item.get("type") == "senses"):
                    continue
                kept, moved, target = [], [], None
                for sense in item["senses"]:
                    if "reading" in sense:
                        other = groups.get((expression, reading_key(sense["reading"], language)))
                        target = other if other is not group else None
                        if target:
                            moved.append((target, []))
                            continue
                    (moved[-1][1] if target else kept).append(sense)
                if not moved:
                    continue
                definition["glossary"][i] = {**item, "senses": kept}
                for other, senses in moved:
                    other["definitions"].append({**definition, "glossary": [{"type": "senses", "senses": senses, "examples": []}]})
