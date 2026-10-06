import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from gui_components.constants import ROOT

DB_PATH = ROOT / "library" / "miningcat.db"

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Imported Yomitan dictionaries. `priority`: lower comes first in lookup results.
CREATE TABLE IF NOT EXISTS dictionaries (
    id              INTEGER PRIMARY KEY,
    title           TEXT NOT NULL,
    revision        TEXT,
    language        TEXT NOT NULL,        -- language of the headwords: ja, zh, yue, ko, fr...
    target_language TEXT,
    author          TEXT,
    url             TEXT,
    description     TEXT,
    attribution     TEXT,
    enabled         INTEGER NOT NULL DEFAULT 1,
    priority        INTEGER NOT NULL DEFAULT 0,
    term_count      INTEGER NOT NULL DEFAULT 0,
    meta_count      INTEGER NOT NULL DEFAULT 0,
    kanji_count     INTEGER NOT NULL DEFAULT 0,
    imported        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS terms (
    id         INTEGER PRIMARY KEY,
    dict_id    INTEGER NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
    expression TEXT NOT NULL,
    reading    TEXT NOT NULL,
    def_tags   TEXT NOT NULL DEFAULT '',
    rules      TEXT NOT NULL DEFAULT '',  -- parts of speech used by deinflection (v5, v1, adj-i...)
    score      INTEGER NOT NULL DEFAULT 0,
    glossary   TEXT NOT NULL,             -- JSON, as in the dictionary (strings or structured content)
    sequence   INTEGER,
    term_tags  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS terms_expression ON terms(expression);
CREATE INDEX IF NOT EXISTS terms_reading ON terms(reading);
CREATE INDEX IF NOT EXISTS terms_dict ON terms(dict_id);

-- Frequency / pitch / IPA data (term_meta_bank).
CREATE TABLE IF NOT EXISTS term_meta (
    dict_id    INTEGER NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
    expression TEXT NOT NULL,
    mode       TEXT NOT NULL,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS term_meta_expression ON term_meta(expression);
CREATE INDEX IF NOT EXISTS term_meta_dict ON term_meta(dict_id);

-- Single characters (kanji_bank): readings and meanings of 字 / 漢字. For Chinese dictionaries,
-- `onyomi` holds the pinyin (or jyutping) and `kunyomi` is empty.
CREATE TABLE IF NOT EXISTS kanji (
    dict_id   INTEGER NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
    character TEXT NOT NULL,
    onyomi    TEXT NOT NULL DEFAULT '',
    kunyomi   TEXT NOT NULL DEFAULT '',
    tags      TEXT NOT NULL DEFAULT '',
    meanings  TEXT NOT NULL,              -- JSON list of strings
    stats     TEXT NOT NULL DEFAULT '{}'  -- JSON: stroke count, grade, JLPT level...
);
CREATE INDEX IF NOT EXISTS kanji_character ON kanji(character);
CREATE INDEX IF NOT EXISTS kanji_dict ON kanji(dict_id);

-- Character frequencies (kanji_meta_bank).
CREATE TABLE IF NOT EXISTS kanji_meta (
    dict_id   INTEGER NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
    character TEXT NOT NULL,
    mode      TEXT NOT NULL,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS kanji_meta_character ON kanji_meta(character);

CREATE TABLE IF NOT EXISTS tags (
    dict_id  INTEGER NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    ord      INTEGER NOT NULL DEFAULT 0,
    notes    TEXT NOT NULL DEFAULT '',
    score    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tags_dict ON tags(dict_id, name);

-- The user's words. A word belongs to one language: knowing 説 in Mandarin says nothing about
-- Cantonese. Status: learning, known or ignored (a word that isn't here is new).
CREATE TABLE IF NOT EXISTS words (
    id            INTEGER PRIMARY KEY,
    language      TEXT NOT NULL,
    expression    TEXT NOT NULL,
    reading       TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL CHECK (status IN ('learning', 'known', 'ignored')),
    source        TEXT NOT NULL DEFAULT 'manual',   -- manual, card, anki
    anki_note_id  INTEGER,
    anki_interval INTEGER,
    created       REAL NOT NULL,
    updated       REAL NOT NULL,
    UNIQUE (language, expression, reading)
);
CREATE INDEX IF NOT EXISTS words_lookup ON words(language, expression);
CREATE INDEX IF NOT EXISTS words_note ON words(anki_note_id);

-- Cards made in the card creator. pending: waiting for Anki; sent: in Anki; failed: Anki refused it;
-- exported: written to an .apkg file.
CREATE TABLE IF NOT EXISTS cards (
    id           INTEGER PRIMARY KEY,
    language     TEXT NOT NULL,
    expression   TEXT NOT NULL,
    reading      TEXT NOT NULL DEFAULT '',
    fields       TEXT NOT NULL,           -- JSON: MiningCat fields (word, reading, definition, sentence...)
    media        TEXT NOT NULL DEFAULT '{}',  -- JSON: {"image": {...}, "audio": {...}}
    tags         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    error        TEXT,
    anki_note_id INTEGER,
    created      REAL NOT NULL,
    updated      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_status ON cards(status);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_init_lock = threading.Lock()
_initialized: set[str] = set()


def _initialize(conn: sqlite3.Connection, path: Path) -> None:
    with _init_lock:
        if str(path) in _initialized:
            return
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
        _initialized.add(str(path))


# Columns added after a database was created (CREATE TABLE IF NOT EXISTS doesn't add them).
_ADDED_COLUMNS = [
    ("dictionaries", "kanji_count", "INTEGER NOT NULL DEFAULT 0"),
    # Yomitan's frequencyMode: "rank-based" (1 = most frequent, also JSON and text lists) or "occurrence-based" (a count)
    ("dictionaries", "freq_mode", "TEXT NOT NULL DEFAULT ''"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, definition in _ADDED_COLUMNS:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    _initialize(conn, path)
    return conn


@contextmanager
def session(path: Path | None = None):
    """A connection committed on success, rolled back on error, always closed."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(key: str, default=None):
    with session() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with session() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def reset_cache() -> None:
    """Forgets which databases were initialized (tests point DB_PATH to temporary files)."""
    with _init_lock:
        _initialized.clear()
