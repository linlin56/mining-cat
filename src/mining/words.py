import time

from mining import db
from mining.languages import (
    CHINESE_LANGUAGES, LANGUAGES, chinese_counterpart, chinese_script, normalize_reading,
    to_simplified, to_traditional,
)

STATUSES = ("learning", "known", "ignored")
SCRIPTS = ("traditional", "simplified", "both")
# Interval (days) from which a card counts as known: Anki's definition of a mature card.
DEFAULT_KNOWN_INTERVAL = 21


class WordError(ValueError):
    pass


def chinese_script_preference(language: str) -> str:
    prefs = db.get_setting("chinese_scripts", {}) or {}
    return prefs.get(language, "both")


def set_chinese_script_preference(language: str, script: str) -> None:
    if language not in CHINESE_LANGUAGES or script not in SCRIPTS:
        raise WordError("Invalid script setting.")
    prefs = db.get_setting("chinese_scripts", {}) or {}
    prefs[language] = script
    db.set_setting("chinese_scripts", prefs)


# How Mandarin readings are shown in the popup and written on cards. Words stay identified by their pinyin.
READING_SYSTEMS = ("pinyin", "zhuyin")


def reading_system(language: str) -> str:
    return (db.get_setting("reading_systems", {}) or {}).get(language, "pinyin") if language == "zh" else ""


def set_reading_system(language: str, system: str) -> None:
    if language != "zh" or system not in READING_SYSTEMS:
        raise WordError("Invalid reading setting.")
    prefs = db.get_setting("reading_systems", {}) or {}
    prefs[language] = system
    db.set_setting("reading_systems", prefs)


def display_reading(language: str, expression: str, reading: str) -> str:
    """The reading as the user wants to see it, whichever the dictionary uses: zhuyin or pinyin, as chosen."""
    if reading and language == "zh":
        from mining.zhuyin import is_zhuyin, pinyin_to_zhuyin, zhuyin_to_pinyin

        if reading_system(language) == "zhuyin":
            return pinyin_to_zhuyin(reading) or reading
        if is_zhuyin(reading):
            return zhuyin_to_pinyin(reading) or reading
    return reading


def preferred_form(language: str, expression: str, preference: str | None = None) -> str:
    """The form under which a word is saved, given the script the user learns (`preference`, read from the
    settings when not given: pass it for many words)."""
    if language not in CHINESE_LANGUAGES:
        return expression
    preference = preference or chinese_script_preference(language)
    script = chinese_script(expression)
    # A word written the same way in both scripts (了解, 台灣's 台...) is kept as it is.
    if preference == "traditional" and script in ("simplified", "mixed"):
        return to_traditional(expression, language)
    if preference == "simplified" and script in ("traditional", "mixed"):
        return to_simplified(expression, language)
    return expression


def _row(row) -> dict:
    return {key: row[key] for key in row.keys()}


def find(conn, language: str, expression: str, reading: str = "") -> dict | None:
    reading = normalize_reading(reading, language)
    rows = conn.execute(
        "SELECT * FROM words WHERE language = ? AND expression = ?", (language, expression)
    ).fetchall()
    exact = next((r for r in rows if r["reading"] == reading), None)
    if exact is not None:
        return _row(exact)
    # A word saved without a reading, or looked up without one, matches any reading.
    loose = next((r for r in rows if not r["reading"] or not reading), None)
    return _row(loose) if loose is not None else None


def status_of(language: str, expression: str, reading: str = "") -> dict:
    """Status of a word, and for Chinese the status of the same word in the other script."""
    with db.session() as conn:
        word = find(conn, language, expression, reading)
        result = {"status": word["status"] if word else "new", "source": word["source"] if word else None}
        if language in CHINESE_LANGUAGES:
            other = chinese_counterpart(expression, language)
            if other is not None:
                script, other_expression = other
                linked = find(conn, language, other_expression, reading)
                if linked and linked["status"] in ("learning", "known"):
                    result["linked"] = {"script": script, "expression": other_expression, "status": linked["status"]}
    return result


def set_status(language: str, expression: str, reading: str, status: str | None,
               source: str = "manual", anki_note_id: int | None = None, anki_interval: int | None = None) -> dict:
    """Sets (or with status=None, clears) the status of a word. Returns the new status."""
    if language not in LANGUAGES:
        raise WordError(f"Unknown language: {language}")
    if status is not None and status not in STATUSES:
        raise WordError(f"Unknown status: {status}")
    expression = (expression or "").strip()
    if not expression:
        raise WordError("Missing word.")
    reading = normalize_reading(reading, language)
    now = time.time()
    with db.session() as conn:
        word = find(conn, language, expression, reading)
        if status is None:
            if word:
                conn.execute("DELETE FROM words WHERE id = ?", (word["id"],))
            return {"status": "new"}
        if word:
            conn.execute(
                "UPDATE words SET status = ?, source = ?, reading = CASE WHEN reading = '' THEN ? ELSE reading END,"
                " anki_note_id = COALESCE(?, anki_note_id), anki_interval = COALESCE(?, anki_interval), updated = ?"
                " WHERE id = ?",
                (status, source, reading, anki_note_id, anki_interval, now, word["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO words(language, expression, reading, status, source, anki_note_id, anki_interval, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (language, expression, reading, status, source, anki_note_id, anki_interval, now, now),
            )
    return {"status": status}


def list_words(language: str | None = None, status: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    query, params = "SELECT * FROM words WHERE 1 = 1", []
    if language:
        query += " AND language = ?"
        params.append(language)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY updated DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with db.session() as conn:
        return [_row(r) for r in conn.execute(query, params).fetchall()]


def counts() -> dict:
    with db.session() as conn:
        rows = conn.execute("SELECT language, status, COUNT(*) AS n FROM words GROUP BY language, status").fetchall()
    result: dict[str, dict] = {}
    for r in rows:
        result.setdefault(r["language"], {})[r["status"]] = r["n"]
    return result


def statuses_for(language: str, expressions: list[str]) -> dict[str, str]:
    """Status of many expressions at once (any reading), e.g. to colour a text."""
    result: dict[str, str] = {}
    unique = list(dict.fromkeys(e for e in expressions if e))
    with db.session() as conn:
        for start in range(0, len(unique), 500):
            chunk = unique[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for r in conn.execute(
                f"SELECT expression, status FROM words WHERE language = ? AND expression IN ({marks})", [language, *chunk]
            ):
                # learning wins over known when readings disagree: the user is still working on it
                if result.get(r["expression"]) != "learning":
                    result[r["expression"]] = r["status"]
    return result


def apply_anki_state(language: str, expression: str, reading: str, note_id: int | None,
                     interval: int, known_interval: int = DEFAULT_KNOWN_INTERVAL) -> str:
    """Updates a word from its Anki cards. A word the user marked known or ignored stays as it is."""
    status = "known" if interval >= known_interval else "learning"
    with db.session() as conn:
        word = find(conn, language, expression, reading)
    if word and word["source"] == "manual" and word["status"] in ("known", "ignored"):
        return word["status"]
    set_status(language, expression, reading, status, source="anki", anki_note_id=note_id, anki_interval=interval)
    return status


__all__ = [
    "STATUSES", "SCRIPTS", "WordError", "chinese_script", "chinese_script_preference",
    "set_chinese_script_preference", "preferred_form", "status_of", "set_status", "list_words",
    "counts", "statuses_for", "apply_anki_state",
]
