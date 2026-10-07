import json
import threading

from mining import db, languages
from mining.languages import CHINESE_LANGUAGES

SETTING = "frequency_lists"  # {language: dictionary id}
LIMIT_BASE = 1000
LIMIT_PER_KNOWN_WORD = 2

_lock = threading.Lock()
_ranks: dict[int, tuple[tuple, dict[str, int]]] = {}       # dict id -> (key, {expression: rank})
_known: dict[str, tuple[tuple, int]] = {}                  # language -> (key, words of the list known)


def lists(language: str) -> list[dict]:
    """The dictionaries of a language that have word frequencies, in the dictionary order."""
    with db.session() as conn:
        rows = conn.execute(
            "SELECT d.id, d.title, d.enabled, d.imported FROM dictionaries d WHERE d.language = ? AND d.meta_count > 0"
            " AND EXISTS (SELECT 1 FROM term_meta m WHERE m.dict_id = d.id AND m.mode = 'freq') ORDER BY d.priority, d.id",
            (language,),
        ).fetchall()
    return [{"id": r["id"], "title": r["title"], "enabled": bool(r["enabled"]), "imported": r["imported"]} for r in rows]


def reference(language: str) -> dict | None:
    """The frequency list used for the language: the one chosen in the settings, else the first enabled one."""
    available = [d for d in lists(language) if d["enabled"]]
    chosen = (db.get_setting(SETTING, {}) or {}).get(language)
    return next((d for d in available if d["id"] == chosen), available[0] if available else None)


def choose(language: str, dict_id: int | None) -> None:
    if dict_id is not None and dict_id not in {d["id"] for d in lists(language)}:
        raise ValueError("This dictionary has no word frequencies.")
    chosen = dict(db.get_setting(SETTING, {}) or {})
    chosen[language] = dict_id
    db.set_setting(SETTING, chosen)


# A frequency of term_meta: 1234, {"value": 1234, "displayValue": "1234㋕"}, or {"reading": ..., "frequency": either}.
def _value(data) -> float | None:
    if isinstance(data, dict) and "frequency" in data:
        data = data["frequency"]
    if isinstance(data, dict):
        data = data.get("value")
    return data if isinstance(data, (int, float)) and not isinstance(data, bool) else None


def ranks(dict_id: int, imported: float = 0) -> dict[str, int]:
    """{expression: rank} of a frequency list, 1 being the most frequent word."""
    with _lock:
        cached = _ranks.get(dict_id)
        if cached and cached[0] == (str(db.DB_PATH), imported):
            return cached[1]
    with db.session() as conn:
        mode = conn.execute("SELECT freq_mode FROM dictionaries WHERE id = ?", (dict_id,)).fetchone()
        rows = conn.execute("SELECT expression, data FROM term_meta WHERE dict_id = ? AND mode = 'freq'", (dict_id,)).fetchall()
    values: dict[str, float] = {}
    occurrences = bool(mode) and mode["freq_mode"] == "occurrence-based"
    for r in rows:
        value = _value(json.loads(r["data"]))
        if value is None:
            continue
        best = values.get(r["expression"])
        # a word with several readings keeps its most frequent one
        if best is None or (value > best if occurrences else value < best):
            values[r["expression"]] = value
    if occurrences:
        ordered = sorted(values, key=values.get, reverse=True)
        result = {expression: i + 1 for i, expression in enumerate(ordered)}
    else:
        result = {expression: max(1, int(value)) for expression, value in values.items()}
    with _lock:
        _ranks[dict_id] = ((str(db.DB_PATH), imported), result)
    return result


def _variants(language: str, words: tuple[str, ...]) -> list[str]:
    found = [w for w in dict.fromkeys(words) if w]
    if language in CHINESE_LANGUAGES:
        # a list in one script still ranks the words of the other (説 / 说)
        found += [v for w in list(found) for v in (languages.to_simplified(w, language), languages.to_traditional(w, language)) if v not in found]
    return found


def rank_in(table: dict[str, int], language: str, *words: str) -> int | None:
    """Rank of a word in a list, from any of its spellings (dictionary headword, form saved by the user...)."""
    direct = [table[w] for w in words if w in table]
    if direct:
        return min(direct)
    found = [table[w] for w in _variants(language, words) if w in table]
    return min(found) if found else None


def known_in_list(language: str, ref: dict, table: dict[str, int]) -> int:
    with db.session() as conn:
        key = tuple(conn.execute(
            "SELECT COUNT(*), MAX(updated) FROM words WHERE language = ? AND status = 'known'", (language,)).fetchone())
        key = (str(db.DB_PATH), ref["id"], ref["imported"], *key)
        with _lock:
            cached = _known.get(language)
            if cached and cached[0] == key:
                return cached[1]
        expressions = [r[0] for r in conn.execute(
            "SELECT DISTINCT expression FROM words WHERE language = ? AND status = 'known'", (language,))]
    count = sum(1 for e in expressions if rank_in(table, language, e) is not None)
    with _lock:
        _known[language] = (key, count)
    return count


def _frontier(language: str, ref: dict, table: dict[str, int]) -> dict:
    known = known_in_list(language, ref, table)
    return {"dictionary": {"id": ref["id"], "title": ref["title"]}, "known": known, "words": len(table),
            "limit": LIMIT_BASE + LIMIT_PER_KNOWN_WORD * known}


def frontier(language: str) -> dict | None:
    """{"dictionary", "known", "words", "limit"} of the language's frequency list, or None when it has none."""
    return Ranker(language).frontier


class Ranker:
    """Ranks of many words in the language's frequency list, and its limit (frontier None without a list)."""

    def __init__(self, language: str):
        self.language = language
        ref = reference(language)
        self.table = ranks(ref["id"], ref["imported"]) if ref else {}
        self.frontier = _frontier(language, ref, self.table) if ref else None

    def rank(self, *words: str) -> int | None:
        return rank_in(self.table, self.language, *words) if self.table else None

    def frequent(self, *words: str) -> bool:
        """Whether a word is frequent enough to be recommended (any word, without a frequency list)."""
        if self.frontier is None:
            return True
        rank = self.rank(*words)
        return rank is not None and rank <= self.frontier["limit"]


def clear_cache() -> None:
    with _lock:
        _ranks.clear()
        _known.clear()
