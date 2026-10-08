import json
import sqlite3

from miningcat.domain.text.scripts import HAN_CHARACTER

# Character details kept for the popup: the rest of a kanji dictionary's stats are reference numbers.
_KANJI_STATS = ("strokes", "grade", "jlpt", "freq")


class DictionaryQueries:
    """What lookups, segmentation, frequency lists and sentence readings read from the enabled dictionaries."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def enabled_dictionaries(self, language: str) -> dict[int, dict]:
        rows = self._conn.execute(
            "SELECT id, title, priority FROM dictionaries WHERE enabled = 1 AND language = ? ORDER BY priority, id",
            (language,),
        ).fetchall()
        return {r["id"]: {"id": r["id"], "title": r["title"], "priority": r["priority"]} for r in rows}

    def terms(self, dict_ids: list[int], texts: list[str]):
        dict_marks = ",".join("?" * len(dict_ids))
        for start in range(0, len(texts), 400):
            chunk = texts[start:start + 400]
            marks = ",".join("?" * len(chunk))
            yield from self._conn.execute(
                f"SELECT * FROM terms WHERE dict_id IN ({dict_marks}) AND (expression IN ({marks}) OR reading IN ({marks}))",
                [*dict_ids, *chunk, *chunk],
            )

    def frequencies(self, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list]:
        if not expressions or not dict_ids:
            return {}
        ids = list(dict_ids)
        marks = ",".join("?" * len(expressions))
        result: dict[str, list] = {}
        for r in self._conn.execute(
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
    def pronunciations(self, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list]:
        if not expressions or not dict_ids:
            return {}
        ids = list(dict_ids)
        result: dict[str, list] = {}
        for r in self._conn.execute(
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

    def tag_notes(self, dict_id: int, names: set[str]) -> dict[str, dict]:
        if not names:
            return {}
        marks = ",".join("?" * len(names))
        return {
            r["name"]: {"category": r["category"], "notes": r["notes"]}
            for r in self._conn.execute(f"SELECT name, category, notes FROM tags WHERE dict_id = ? AND name IN ({marks})", [dict_id, *names])
        }

    # Character dictionary entries of the Chinese characters / kanji of `expressions`: {character: [entries]}.
    def characters(self, dict_ids: dict[int, dict], expressions: list[str]) -> dict[str, list[dict]]:
        chars = list(dict.fromkeys(c for e in expressions for c in HAN_CHARACTER.findall(e)))
        if not chars or not dict_ids:
            return {}
        ids = list(dict_ids)
        id_marks, char_marks = ",".join("?" * len(ids)), ",".join("?" * len(chars))
        freqs: dict[str, list] = {}
        for r in self._conn.execute(
            f"SELECT dict_id, character, data FROM kanji_meta WHERE mode = 'freq' AND dict_id IN ({id_marks})"
            f" AND character IN ({char_marks})", [*ids, *chars],
        ):
            data = json.loads(r["data"])
            value = data.get("displayValue", data.get("value")) if isinstance(data, dict) else data
            freqs.setdefault(r["character"], []).append(f"{dict_ids[r['dict_id']]['title'].split(' [')[0]} {value}")
        result: dict[str, list[dict]] = {}
        rows = self._conn.execute(
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

    def signature(self, language: str) -> tuple:
        """Changes whenever a dictionary of the language is imported, removed, enabled or disabled."""
        rows = self._conn.execute(
            "SELECT id, enabled, imported, term_count FROM dictionaries WHERE language = ? ORDER BY id", (language,),
        ).fetchall()
        return tuple(tuple(r) for r in rows)

    def headwords(self, language: str):
        """(expression, reading, rules, def_tags, score) of every term of the enabled dictionaries of a language."""
        return self._conn.execute(
            "SELECT t.expression, t.reading, t.rules, t.def_tags, t.score FROM terms t JOIN dictionaries d ON d.id = t.dict_id"
            " WHERE d.enabled = 1 AND d.language = ?", (language,),
        )

    def frequency_lists(self, language: str) -> list[dict]:
        """The dictionaries of a language that have word frequencies, in the dictionary order."""
        rows = self._conn.execute(
            "SELECT d.id, d.title, d.enabled, d.imported FROM dictionaries d WHERE d.language = ? AND d.meta_count > 0"
            " AND EXISTS (SELECT 1 FROM term_meta m WHERE m.dict_id = d.id AND m.mode = 'freq') ORDER BY d.priority, d.id",
            (language,),
        ).fetchall()
        return [{"id": r["id"], "title": r["title"], "enabled": bool(r["enabled"]), "imported": r["imported"]} for r in rows]

    def counts_occurrences(self, dict_id: int) -> bool:
        """Whether a frequency list gives counts ("occurrence-based") instead of ranks."""
        row = self._conn.execute("SELECT freq_mode FROM dictionaries WHERE id = ?", (dict_id,)).fetchone()
        return bool(row) and row["freq_mode"] == "occurrence-based"

    def frequencies_of_list(self, dict_id: int) -> list[tuple[str, str]]:
        """(expression, JSON data) of every word of a frequency list."""
        return [tuple(r) for r in self._conn.execute(
            "SELECT expression, data FROM term_meta WHERE dict_id = ? AND mode = 'freq'", (dict_id,))]

    def readings(self, language: str, headwords: list[str]):
        """(expression, reading, glossary) of the entries of some headwords, the first dictionary first."""
        unique = list(dict.fromkeys(h for h in headwords if h))
        for start in range(0, len(unique), 400):
            chunk = unique[start:start + 400]
            yield from self._conn.execute(
                "SELECT t.expression, t.reading, t.glossary FROM terms t JOIN dictionaries d ON d.id = t.dict_id"
                f" WHERE d.enabled = 1 AND d.language = ? AND t.expression IN ({','.join('?' * len(chunk))})"
                " ORDER BY d.priority, t.id", [language, *chunk],
            ).fetchall()
