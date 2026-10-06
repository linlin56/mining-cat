import json
import re

from mining import db
from mining.deinflect import Deinflection, transformer_for
from mining.languages import (
    CHINESE_LANGUAGES, chinese_counterpart, is_no_space, reading_key, text_variants,
)
from mining import words as words_mod

MAX_SCAN = 20          # characters tried from the cursor in languages without spaces
MAX_WORDS = 5          # words tried from the cursor in other languages
MAX_RESULTS = 12
STRICT_PART_OF_SPEECH = {"ja", "ko"}

_WORD_END = re.compile(r"[\w’'\-]+", re.UNICODE)
_HAN_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff]")
# Character details kept for the popup: the rest of a kanji dictionary's stats are reference numbers.
_KANJI_STATS = ("strokes", "grade", "jlpt", "freq")


def _sources(text: str, language: str) -> list[str]:
    """Candidate texts starting at the cursor, longest first."""
    text = text.strip("\n")
    if is_no_space(language):
        text = text[:MAX_SCAN]
        return [text[:n] for n in range(len(text), 0, -1) if text[:n].strip()]
    ends = []
    for m in _WORD_END.finditer(text):
        ends.append(m.end())
        if len(ends) >= MAX_WORDS:
            break
    candidates = [text[:end].rstrip("-’'") for end in reversed(ends)]
    # Korean words carry their particles and endings (친구와): the start of the word is a word too.
    if language == "ko" and ends:
        candidates += [text[:end] for end in range(ends[0] - 1, 0, -1)]
    return [c for c in dict.fromkeys(candidates) if c]


def _enabled_dictionaries(conn, language: str) -> dict[int, dict]:
    rows = conn.execute(
        "SELECT id, title, priority FROM dictionaries WHERE enabled = 1 AND language = ? ORDER BY priority, id",
        (language,),
    ).fetchall()
    return {r["id"]: {"id": r["id"], "title": r["title"], "priority": r["priority"]} for r in rows}


def _query_terms(conn, dict_ids: list[int], texts: list[str]):
    dict_marks = ",".join("?" * len(dict_ids))
    for start in range(0, len(texts), 400):
        chunk = texts[start:start + 400]
        marks = ",".join("?" * len(chunk))
        yield from conn.execute(
            f"SELECT * FROM terms WHERE dict_id IN ({dict_marks}) AND (expression IN ({marks}) OR reading IN ({marks}))",
            [*dict_ids, *chunk, *chunk],
        )


def _frequencies(conn, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list]:
    if not expressions or not dict_ids:
        return {}
    ids = list(dict_ids)
    marks = ",".join("?" * len(expressions))
    result: dict[str, list] = {}
    for r in conn.execute(
        f"SELECT dict_id, expression, data FROM term_meta WHERE mode = 'freq' AND dict_id IN ({','.join('?' * len(ids))})"
        f" AND expression IN ({marks})", [*ids, *expressions],
    ):
        data = json.loads(r["data"])
        reading = None
        if isinstance(data, dict) and "frequency" in data:
            reading = data.get("reading")
            data = data["frequency"]
        if isinstance(data, dict):
            value, display = data.get("value"), data.get("displayValue")
        else:
            value, display = data, None
        result.setdefault(r["expression"], []).append({
            "dictionary": dict_ids[r["dict_id"]]["title"], "priority": dict_ids[r["dict_id"]]["priority"],
            "reading": reading, "value": value, "display": str(display if display is not None else value),
        })
    return result


# Pitch accents and IPA transcriptions (term_meta "pitch" / "ipa"): {expression: [{dictionary, reading, ...}]}.
def _pronunciations(conn, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list]:
    if not expressions or not dict_ids:
        return {}
    ids = list(dict_ids)
    result: dict[str, list] = {}
    for r in conn.execute(
        f"SELECT dict_id, expression, mode, data FROM term_meta WHERE mode IN ('pitch', 'ipa')"
        f" AND dict_id IN ({','.join('?' * len(ids))}) AND expression IN ({','.join('?' * len(expressions))})",
        [*ids, *expressions],
    ):
        data = json.loads(r["data"])
        if not isinstance(data, dict):
            continue
        item = {"dictionary": dict_ids[r["dict_id"]]["title"], "priority": dict_ids[r["dict_id"]]["priority"],
                "reading": str(data.get("reading") or "")}
        if r["mode"] == "pitch":
            positions = [p.get("position") for p in data.get("pitches") or [] if isinstance(p, dict)]
            # a pattern written as "HLL" instead of a downstep position is kept as text
            item["pitches"] = [p for p in positions if isinstance(p, (int, str))]
        else:
            item["ipa"] = [t.get("ipa") for t in data.get("transcriptions") or [] if isinstance(t, dict) and t.get("ipa")]
        result.setdefault(r["expression"], []).append(item)
    return result


def _tag_notes(conn, dict_id: int, names: set[str]) -> dict[str, dict]:
    if not names:
        return {}
    marks = ",".join("?" * len(names))
    return {
        r["name"]: {"category": r["category"], "notes": r["notes"]}
        for r in conn.execute(f"SELECT name, category, notes FROM tags WHERE dict_id = ? AND name IN ({marks})", [dict_id, *names])
    }


# Character dictionary entries of the Chinese characters / kanji of `expressions`: {character: [entries]}.
def characters(conn, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list[dict]]:
    chars = list(dict.fromkeys(c for e in expressions for c in _HAN_CHAR.findall(e)))
    if not chars or not dict_ids:
        return {}
    ids = list(dict_ids)
    id_marks, char_marks = ",".join("?" * len(ids)), ",".join("?" * len(chars))
    freqs: dict[str, list] = {}
    for r in conn.execute(
        f"SELECT dict_id, character, data FROM kanji_meta WHERE mode = 'freq' AND dict_id IN ({id_marks})"
        f" AND character IN ({char_marks})", [*ids, *chars],
    ):
        data = json.loads(r["data"])
        value = data.get("displayValue", data.get("value")) if isinstance(data, dict) else data
        freqs.setdefault(r["character"], []).append(f"{dict_ids[r['dict_id']]['title'].split(' [')[0]} {value}")
    result: dict[str, list[dict]] = {}
    rows = conn.execute(
        f"SELECT * FROM kanji WHERE dict_id IN ({id_marks}) AND character IN ({char_marks})", [*ids, *chars],
    ).fetchall()
    for r in sorted(rows, key=lambda r: dict_ids[r["dict_id"]]["priority"]):
        stats = json.loads(r["stats"])
        result.setdefault(r["character"], []).append({
            "dictionary": dict_ids[r["dict_id"]]["title"],
            "onyomi": r["onyomi"].split(), "kunyomi": r["kunyomi"].split(),
            "meanings": json.loads(r["meanings"]),
            "stats": {k: stats[k] for k in _KANJI_STATS if k in stats},
            "frequencies": freqs.get(r["character"], []),
        })
    return result


# Whether reading `a` should be shown rather than `b` for the same pronunciation: tone marks (xíng) over numbers (xing2).
def _readable(a: str, b: str) -> bool:
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
    before it) isn't repeated. Senses tagged differently (JMdict's numbered senses, parts of speech) stay apart."""
    merged: list[dict] = []
    by_tags: dict[tuple, dict] = {}
    seen: set[str] = set()
    for definition in definitions:
        glossary = definition["glossary"] if isinstance(definition["glossary"], list) else [definition["glossary"]]
        fresh = []
        for item in glossary:
            key = _gloss_key(item)
            if key and key not in seen:
                seen.add(key)
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


def lookup(language: str, text: str) -> dict:
    """Entries for `text` (the text from the cursor onwards), longest match first."""
    sources = _sources(text, language)
    if not sources:
        return {"entries": [], "dictionaries": 0, "language": language}
    transformer = transformer_for(language)

    # deinflected text -> list of (source, deinflection)
    candidates: dict[str, list[tuple[str, Deinflection]]] = {}
    for source in sources:
        for variant in text_variants(source, language):
            deinflections = transformer.transform(variant) if transformer else [Deinflection(variant, 0, ())]
            for d in deinflections:
                candidates.setdefault(d.text, []).append((source, d))

    with db.session() as conn:
        dicts = _enabled_dictionaries(conn, language)
        if not dicts:
            return {"entries": [], "dictionaries": 0, "language": language}
        # best match of each dictionary row
        matches: dict[int, tuple] = {}
        # Japanese and Korean dictionaries always give parts of speech, so a deinflected form must fit
        # them (like Yomitan). Other dictionaries often don't: an entry without any is accepted.
        strict = language in STRICT_PART_OF_SPEECH
        for row in _query_terms(conn, list(dicts), list(candidates)):
            pos_flags = transformer.flags_for_parts_of_speech(row["rules"].split()) if transformer else 0
            for key in (row["expression"], row["reading"]):
                for source, d in candidates.get(key, ()):
                    if transformer and not transformer.conditions_match(d.conditions, pos_flags):
                        if strict or row["rules"].strip():
                            continue
                    rank = (len(source), -len(d.trace), key == row["expression"])
                    best = matches.get(row["id"])
                    if best is None or rank > best[0]:
                        matches[row["id"]] = (rank, source, d, row)

        # group the rows of every dictionary by headword and pronunciation: 行 xíng and 行 háng are two entries,
        # 行 xíng from two dictionaries (or two rows of one) is one, whether written xíng or xing2
        groups: dict[tuple, dict] = {}
        for rank, source, d, row in matches.values():
            reading = row["reading"] or row["expression"]
            key = (row["expression"], reading_key(reading, language))
            group = groups.get(key)
            if group is None or rank > group["rank"]:
                kept = group["definitions"] if group else []
                if group and _readable(group["reading"], reading):
                    reading = group["reading"]
                group = {
                    "rank": rank, "expression": row["expression"], "reading": reading,
                    "source": source, "length": len(source),
                    "inflections": transformer.describe(tuple(reversed(d.trace))) if transformer and d.trace else [],
                    "definitions": kept, "score": row["score"],
                }
                groups[key] = group
            elif _readable(reading, group["reading"]):
                group["reading"] = reading
            dictionary = dicts[row["dict_id"]]
            group["definitions"].append({
                "dictionary": dictionary["title"], "dict_id": dictionary["id"], "priority": dictionary["priority"],
                "tags": [t for t in row["def_tags"].split() if t], "term_tags": [t for t in row["term_tags"].split() if t],
                "glossary": json.loads(row["glossary"]), "score": row["score"], "sequence": row["sequence"],
                "row": row["id"],
            })
            group["score"] = max(group["score"], row["score"])

        freqs = _frequencies(conn, dicts, list({g["expression"] for g in groups.values()}))
        sounds = _pronunciations(conn, dicts, list({g["expression"] for g in groups.values()}))
        for g in groups.values():
            g["frequencies"] = [
                f for f in sorted(freqs.get(g["expression"], []), key=lambda f: f["priority"])
                if not f["reading"] or reading_key(f["reading"], language) == reading_key(g["reading"], language)
            ]
            g["pronunciations"] = [
                {k: v for k, v in p.items() if k != "priority"} for p in sorted(sounds.get(g["expression"], []), key=lambda p: p["priority"])
                if not p["reading"] or reading_key(p["reading"], language) == reading_key(g["reading"], language)
            ]
            # rank in the first frequency list that has the word (smaller = more frequent)
            g["frequency_rank"] = next((f["value"] for f in g["frequencies"] if isinstance(f["value"], (int, float))), float("inf"))

        ordered = sorted(
            groups.values(),
            key=lambda g: (-g["rank"][0], -g["rank"][1], not g["rank"][2], g["frequency_rank"],
                           min(x["priority"] for x in g["definitions"]), -g["score"]),
        )[:MAX_RESULTS]

        tag_cache: dict[int, dict] = {}
        for g in ordered:
            g["definitions"].sort(key=lambda x: (x["priority"], x["row"]))  # senses keep the dictionary's order
            g["definitions"] = merge_definitions(g["definitions"])
            for definition in g["definitions"]:
                names = set(definition["tags"]) | set(definition["term_tags"])
                notes = _tag_notes(conn, definition["dict_id"], names - set(tag_cache.get(definition["dict_id"], {})))
                tag_cache.setdefault(definition["dict_id"], {}).update(notes)
                definition["tag_info"] = {n: tag_cache[definition["dict_id"]].get(n, {}) for n in names}
            del g["rank"]
            del g["frequency_rank"]

        found = characters(conn, dicts, [g["expression"] for g in ordered])
        for g in ordered:
            g["characters"] = [{"character": c, "entries": found[c]}
                               for c in dict.fromkeys(_HAN_CHAR.findall(g["expression"])) if c in found]

    for g in ordered:
        form = words_mod.preferred_form(language, g["expression"])
        g["form"] = form
        g["status"] = words_mod.status_of(language, form, g["reading"])
        if language in CHINESE_LANGUAGES:
            g["script"] = words_mod.chinese_script(g["expression"])
            other = chinese_counterpart(g["expression"], language)
            g["counterpart"] = {"script": other[0], "expression": other[1]} if other else None
    return {"entries": ordered, "dictionaries": len(dicts), "language": language}
