import json
import sqlite3
import time


def _card(row: sqlite3.Row) -> dict:
    card = {key: row[key] for key in row.keys()}
    card["fields"] = json.loads(card["fields"])
    card["media"] = json.loads(card["media"])
    return card


class CardRepository:
    """The cards made in the card creator (table `cards`), within a session. Status: pending (waiting for Anki),
    sent (in Anki), failed (Anki refused it) or exported (written to an .apkg file)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, language: str, expression: str, reading: str, fields: dict, media: dict, tags: str) -> int:
        now = time.time()
        return self._conn.execute(
            "INSERT INTO cards(language, expression, reading, fields, media, tags, status, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (language, expression, reading, json.dumps(fields, ensure_ascii=False),
             json.dumps(media, ensure_ascii=False), tags, now, now),
        ).lastrowid

    def get(self, card_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return _card(row) if row is not None else None

    def search(self, status: str | None = None, limit: int = 200, language: str | None = None) -> list[dict]:
        query, conditions, params = "SELECT * FROM cards", [], []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if language:
            conditions.append("language = ?")
            params.append(language)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created DESC LIMIT ?"
        params.append(limit)
        return [_card(r) for r in self._conn.execute(query, params).fetchall()]

    def update(self, card_id: int, **values) -> None:
        values["updated"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in values)
        self._conn.execute(f"UPDATE cards SET {assignments} WHERE id = ?", [*values.values(), card_id])

    def delete(self, card_id: int) -> None:
        self._conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
