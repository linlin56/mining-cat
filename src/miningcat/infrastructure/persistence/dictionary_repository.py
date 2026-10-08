import sqlite3
import time

from miningcat.infrastructure.persistence.database import as_dict


class DictionaryRepository:
    """The imported dictionaries and their rows (terms, frequencies, characters, tags), within a session."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def exists(self, title: str, revision: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM dictionaries WHERE title = ? AND COALESCE(revision, '') = ?", (title, revision),
        ).fetchone() is not None

    def add(self, *, title: str, revision: str, language: str, freq_mode: str = "", meta_count: int = 0,
            target_language: str | None = None, author: str | None = None, url: str | None = None,
            description: str | None = None, attribution: str | None = None) -> int:
        """Adds a dictionary after the others (last in the lookup results). Returns its id."""
        priority = self._conn.execute("SELECT COALESCE(MAX(priority), -1) + 1 FROM dictionaries").fetchone()[0]
        return self._conn.execute(
            "INSERT INTO dictionaries(title, revision, language, target_language, author, url, description,"
            " attribution, priority, imported, freq_mode, meta_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, revision, language, target_language, author, url, description, attribution, priority,
             time.time(), freq_mode, meta_count),
        ).lastrowid

    def add_terms(self, rows) -> None:
        self._conn.executemany(
            "INSERT INTO terms(dict_id, expression, reading, def_tags, rules, score, glossary, sequence, term_tags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    def add_term_meta(self, rows) -> None:
        self._conn.executemany("INSERT INTO term_meta(dict_id, expression, mode, data) VALUES (?, ?, ?, ?)", rows)

    def add_kanji(self, rows) -> None:
        self._conn.executemany(
            "INSERT INTO kanji(dict_id, character, onyomi, kunyomi, tags, meanings, stats) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows)

    def add_kanji_meta(self, rows) -> None:
        self._conn.executemany("INSERT INTO kanji_meta(dict_id, character, mode, data) VALUES (?, ?, ?, ?)", rows)

    def add_tags(self, rows) -> None:
        self._conn.executemany("INSERT INTO tags(dict_id, name, category, ord, notes, score) VALUES (?, ?, ?, ?, ?, ?)",
                               rows)

    def set_counts(self, dict_id: int, terms: int, meta: int, kanji: int) -> None:
        self._conn.execute("UPDATE dictionaries SET term_count = ?, meta_count = ?, kanji_count = ? WHERE id = ?",
                           (terms, meta, kanji, dict_id))

    def all(self) -> list[dict]:
        return [as_dict(r) for r in self._conn.execute("SELECT * FROM dictionaries ORDER BY language, priority, id")]

    def get(self, dict_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM dictionaries WHERE id = ?", (dict_id,)).fetchone()
        return as_dict(row) if row is not None else None

    def set_enabled(self, dict_id: int, enabled: bool) -> None:
        self._conn.execute("UPDATE dictionaries SET enabled = ? WHERE id = ?", (1 if enabled else 0, dict_id))

    def set_language(self, dict_id: int, language: str) -> None:
        self._conn.execute("UPDATE dictionaries SET language = ? WHERE id = ?", (language, dict_id))

    def set_priority(self, dict_id: int, priority: int) -> None:
        self._conn.execute("UPDATE dictionaries SET priority = ? WHERE id = ?", (priority, dict_id))

    def delete(self, dict_id: int) -> None:
        for table in ("terms", "term_meta", "tags", "kanji", "kanji_meta"):
            self._conn.execute(f"DELETE FROM {table} WHERE dict_id = ?", (dict_id,))
        self._conn.execute("DELETE FROM dictionaries WHERE id = ?", (dict_id,))
