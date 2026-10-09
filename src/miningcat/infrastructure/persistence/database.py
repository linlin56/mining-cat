import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from miningcat.config.paths import paths
from miningcat.infrastructure.persistence.schema import ADDED_COLUMNS, SCHEMA, SCHEMA_VERSION


class Database:
    """The SQLite database of the library. Each session gets its own connection; the schema is created (and
    migrated) the first time a database file is opened."""

    def __init__(self, path: Callable[[], Path]):
        self._path = path
        self._init_lock = threading.Lock()
        self._initialized: set[str] = set()

    @property
    def path(self) -> Path:
        return self._path()

    def connect(self) -> sqlite3.Connection:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        self._initialize(conn, path)
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """A connection committed on success, rolled back on error, always closed."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reset_cache(self) -> None:
        """Forgets which database files were initialized (tests use a new one each time)."""
        with self._init_lock:
            self._initialized.clear()

    def _initialize(self, conn: sqlite3.Connection, path: Path) -> None:
        with self._init_lock:
            if str(path) in self._initialized:
                return
            conn.executescript(SCHEMA)
            self._migrate(conn)
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            conn.commit()
            self._initialized.add(str(path))

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        for table, column, definition in ADDED_COLUMNS:
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def as_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


database = Database(lambda: paths.database)
