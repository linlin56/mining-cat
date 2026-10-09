import json

from miningcat.infrastructure.persistence.database import Database, database


class SettingsStore:
    """User settings kept in the database as JSON values (Anki setup, scripts, study language...)."""

    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str, default=None):
        with self._db.session() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value) -> None:
        with self._db.session() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )


settings = SettingsStore(database)
