import sqlite3
import time

from miningcat.infrastructure.persistence.database import as_dict


class InboxRepository:
    """The words sent from an e-reader (table `inbox`), waiting for a card, within a session."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, language: str, word: str, sentence: str, book: str, location: str, sent: float,
            uid: str | None = None) -> int:
        """Adds a word, or returns the id of the one already received with this uid."""
        if uid:
            row = self._conn.execute("SELECT id FROM inbox WHERE uid = ?", (uid,)).fetchone()
            if row is not None:
                return row["id"]
        return self._conn.execute(
            "INSERT INTO inbox(uid, language, word, sentence, book, location, sent, received) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid or None, language, word, sentence, book, location, sent, time.time()),
        ).lastrowid

    def get(self, item_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM inbox WHERE id = ?", (item_id,)).fetchone()
        return as_dict(row) if row is not None else None

    def search(self, language: str | None = None) -> list[dict]:
        """The oldest first: the order they were read in."""
        if language:
            rows = self._conn.execute("SELECT * FROM inbox WHERE language = ? ORDER BY sent, id", (language,))
        else:
            rows = self._conn.execute("SELECT * FROM inbox ORDER BY sent, id")
        return [as_dict(r) for r in rows.fetchall()]

    def words(self, language: str) -> set[str]:
        """The words waiting in a language."""
        return {r["word"] for r in self._conn.execute("SELECT word FROM inbox WHERE language = ?", (language,))}

    def counts(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT language, COUNT(*) AS n FROM inbox GROUP BY language")
        return {r["language"]: r["n"] for r in rows.fetchall()}

    def delete(self, item_id: int) -> None:
        self._conn.execute("DELETE FROM inbox WHERE id = ?", (item_id,))
