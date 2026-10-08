import sqlite3

from miningcat.domain.text.readings import normalize_reading
from miningcat.infrastructure.persistence.database import as_dict

# SQLite limits the number of parameters of a query.
_CHUNK = 500

# Orders of search(): by the last change, or by the date added (see _word), newest or oldest first.
_ADDED = "COALESCE(anki_note_id / 1000.0, created)"
WORD_ORDERS = {"updated": "updated DESC", "added": f"{_ADDED} DESC", "added_asc": f"{_ADDED} ASC"}


def _word(row) -> dict:
    word = as_dict(row)
    # added: when the word was first studied. An Anki note's id is its creation time (ms), older than the row of a
    # word synced from Anki; the others were added in MiningCat.
    word["added"] = word["anki_note_id"] / 1000 if word.get("anki_note_id") else word["created"]
    return word


class WordRepository:
    """The user's words (table `words`), within a database session."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def find(self, language: str, expression: str, reading: str = "") -> dict | None:
        reading = normalize_reading(reading, language)
        rows = self._conn.execute(
            "SELECT * FROM words WHERE language = ? AND expression = ?", (language, expression)
        ).fetchall()
        exact = next((r for r in rows if r["reading"] == reading), None)
        if exact is not None:
            return _word(exact)
        # A word saved without a reading, or looked up without one, matches any reading.
        loose = next((r for r in rows if not r["reading"] or not reading), None)
        return _word(loose) if loose is not None else None

    def insert(self, language: str, expression: str, reading: str, status: str, source: str,
               anki_note_id: int | None, anki_interval: int | None, now: float) -> None:
        self._conn.execute(
            "INSERT INTO words(language, expression, reading, status, source, anki_note_id, anki_interval, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (language, expression, reading, status, source, anki_note_id, anki_interval, now, now),
        )

    def update(self, word_id: int, status: str, source: str, reading: str,
               anki_note_id: int | None, anki_interval: int | None, now: float) -> None:
        """Sets the status of a word, and its reading when it had none."""
        self._conn.execute(
            "UPDATE words SET status = ?, source = ?, reading = CASE WHEN reading = '' THEN ? ELSE reading END,"
            " anki_note_id = COALESCE(?, anki_note_id), anki_interval = COALESCE(?, anki_interval), updated = ?"
            " WHERE id = ?",
            (status, source, reading, anki_note_id, anki_interval, now, word_id),
        )

    def delete(self, word_id: int) -> None:
        self._conn.execute("DELETE FROM words WHERE id = ?", (word_id,))

    def search(self, language: str | None = None, status: str | None = None, limit: int = 500, offset: int = 0,
               order: str = "updated") -> list[dict]:
        query, params = "SELECT * FROM words WHERE 1 = 1", []
        if language:
            query += " AND language = ?"
            params.append(language)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += f" ORDER BY {WORD_ORDERS.get(order, WORD_ORDERS['updated'])}, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        return [_word(r) for r in self._conn.execute(query, params).fetchall()]

    def counts(self) -> dict[str, dict[str, int]]:
        """{language: {status: number of words}}."""
        rows = self._conn.execute("SELECT language, status, COUNT(*) AS n FROM words GROUP BY language, status").fetchall()
        result: dict[str, dict] = {}
        for r in rows:
            result.setdefault(r["language"], {})[r["status"]] = r["n"]
        return result

    def statuses_for(self, language: str, expressions: list[str]) -> dict[str, str]:
        """Status of many expressions at once (any reading)."""
        result: dict[str, str] = {}
        unique = list(dict.fromkeys(e for e in expressions if e))
        for start in range(0, len(unique), _CHUNK):
            chunk = unique[start:start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            for r in self._conn.execute(
                f"SELECT expression, status FROM words WHERE language = ? AND expression IN ({marks})", [language, *chunk]
            ):
                # learning wins over known when readings disagree: the user is still working on it
                if result.get(r["expression"]) != "learning":
                    result[r["expression"]] = r["status"]
        return result

    def known_signature(self, language: str) -> tuple:
        """Changes whenever a known word of the language is added, removed or updated."""
        return tuple(self._conn.execute(
            "SELECT COUNT(*), MAX(updated) FROM words WHERE language = ? AND status = 'known'", (language,)).fetchone())

    def known_expressions(self, language: str) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT DISTINCT expression FROM words WHERE language = ? AND status = 'known'", (language,))]

    def sent_card_words(self) -> list[sqlite3.Row]:
        """Words of the cards sent to Anki from MiningCat (they have the id of their note)."""
        return self._conn.execute(
            "SELECT language, expression, reading, anki_note_id FROM words WHERE source = 'card' AND anki_note_id IS NOT NULL"
        ).fetchall()
