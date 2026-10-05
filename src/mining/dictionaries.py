# dictionaries.py - Imports dictionaries in Yomitan's format into the SQLite database.
#
# A Yomitan dictionary is a zip file with:
#   index.json              title, revision, format (3), optional sourceLanguage/targetLanguage...
#   term_bank_N.json        [expression, reading, definitionTags, rules, score, glossary, sequence, termTags]
#   term_meta_bank_N.json   [expression, "freq" | "pitch" | "ipa", data]
#   tag_bank_N.json         [name, category, order, notes, score]
#   kanji_bank_N.json       [character, onyomi, kunyomi, tags, meanings, stats]: single characters
#   kanji_meta_bank_N.json  [character, "freq", data]
#   any other file          images referenced by structured-content glossaries
# Format 1 dictionaries (older) use [expression, reading, definitionTags, rules, score, *glossary].

import json
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from mining import db
from mining.languages import LANGUAGES, guess_dictionary_language

MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".tif", ".tiff"}
BATCH = 5000


class DictionaryError(ValueError):
    pass


def media_dir(dict_id: int) -> Path:
    return db.DB_PATH.parent / "dictionaries" / str(dict_id)


def _bank_files(zf: zipfile.ZipFile, prefix: str) -> list[str]:
    pattern = re.compile(rf"^(?:.*/)?{prefix}_(\d+)\.json$")
    found = [(int(m.group(1)), name) for name in zf.namelist() if (m := pattern.match(name))]
    return [name for _, name in sorted(found)]


def _read_index(zf: zipfile.ZipFile) -> dict:
    index_name = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "index.json"), None)
    if index_name is None:
        raise DictionaryError("This zip has no index.json: it isn't a Yomitan dictionary.")
    try:
        index = json.loads(zf.read(index_name))
    except ValueError:
        raise DictionaryError("The dictionary's index.json is not valid JSON.")
    if not isinstance(index, dict) or not index.get("title"):
        raise DictionaryError("The dictionary's index.json has no title.")
    return index


def inspect(path: Path) -> dict:
    """Title and guessed language of a dictionary zip, without importing it."""
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise DictionaryError("This file isn't a zip archive.")
    with zf:
        index = _read_index(zf)
        samples = []
        banks = _bank_files(zf, "term_bank")
        if banks:
            for row in json.loads(zf.read(banks[0]))[:2000]:
                if isinstance(row, list) and len(row) >= 2:
                    samples.append((str(row[0]), str(row[1])))
        meta_banks = _bank_files(zf, "term_meta_bank")
        if not samples and meta_banks:
            for row in json.loads(zf.read(meta_banks[0]))[:2000]:
                if isinstance(row, list) and row:
                    samples.append((str(row[0]), ""))
        kanji_banks = _bank_files(zf, "kanji_bank")
        if not samples and kanji_banks:
            # the readings tell the language: on'yomi in katakana for Japanese, pinyin for Chinese
            for row in json.loads(zf.read(kanji_banks[0]))[:2000]:
                if isinstance(row, list) and len(row) >= 3:
                    samples.append((str(row[0]), f"{row[1]} {row[2]}"))
    source_language = index.get("sourceLanguage")
    guess = source_language if source_language else guess_dictionary_language(samples)
    return {
        "title": index["title"],
        "revision": str(index.get("revision", "")),
        "language": guess,
        "has_terms": bool(banks),
        "has_meta": bool(meta_banks),
        "has_kanji": bool(kanji_banks),
    }


def _term_rows(rows: list, dict_id: int, version: int):
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        expression, reading = str(row[0]), str(row[1] or row[0])
        def_tags = row[2] or ""
        rules = row[3] or ""
        score = row[4] if isinstance(row[4], int) else 0
        if version >= 3:
            glossary = row[5] if len(row) > 5 else []
            sequence = row[6] if len(row) > 6 and isinstance(row[6], int) else None
            term_tags = row[7] if len(row) > 7 and isinstance(row[7], str) else ""
        else:
            glossary, sequence, term_tags = row[5:], None, ""
        yield (dict_id, expression, reading, def_tags, rules, score,
               json.dumps(glossary, ensure_ascii=False, separators=(",", ":")), sequence, term_tags)


# Only single characters are kept: some dictionaries (CC-CEDICT Hanzi) also put whole words in their kanji banks.
def _kanji_rows(rows: list, dict_id: int):
    for row in rows:
        if not isinstance(row, list) or len(row) < 5 or len(str(row[0])) != 1:
            continue
        meanings = [str(m) for m in row[4]] if isinstance(row[4], list) else [str(row[4])]
        stats = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
        yield (dict_id, str(row[0]), str(row[1] or ""), str(row[2] or ""), str(row[3] or ""),
               json.dumps(meanings, ensure_ascii=False), json.dumps(stats, ensure_ascii=False))


def import_dictionary(path: Path, language: str = "", progress=None) -> dict:
    """Imports a dictionary zip. `progress(fraction, message)` is called along the way."""
    progress = progress or (lambda fraction, message: None)
    info = inspect(path)
    language = language or info["language"]
    if not language:
        raise DictionaryError("Couldn't tell which language this dictionary is for: pick it in the list.")
    if language not in LANGUAGES:
        raise DictionaryError(f"Unsupported language: {language}")

    with zipfile.ZipFile(path) as zf:
        index = _read_index(zf)
        version = int(index.get("format", index.get("version", 3)) or 3)
        term_banks = _bank_files(zf, "term_bank")
        meta_banks = _bank_files(zf, "term_meta_bank")
        tag_banks = _bank_files(zf, "tag_bank")
        kanji_banks = _bank_files(zf, "kanji_bank")
        kanji_meta_banks = _bank_files(zf, "kanji_meta_bank")
        if not term_banks and not meta_banks and not kanji_banks and not kanji_meta_banks:
            raise DictionaryError("This dictionary has no terms, characters or frequency data.")

        with db.session() as conn:
            duplicate = conn.execute(
                "SELECT id FROM dictionaries WHERE title = ? AND COALESCE(revision, '') = ?",
                (index["title"], str(index.get("revision", ""))),
            ).fetchone()
            if duplicate:
                raise DictionaryError(f"“{index['title']}” is already imported.")
            priority = conn.execute("SELECT COALESCE(MAX(priority), -1) + 1 FROM dictionaries").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO dictionaries(title, revision, language, target_language, author, url, description,"
                " attribution, priority, imported) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (index["title"], str(index.get("revision", "")), language, index.get("targetLanguage"),
                 index.get("author"), index.get("url"), index.get("description"), index.get("attribution"),
                 priority, time.time()),
            )
            dict_id = cur.lastrowid

        try:
            total_steps = max(1, len(term_banks) + len(meta_banks) + len(kanji_banks) + 1)
            step = 0
            term_count = meta_count = kanji_count = 0
            with db.session() as conn:
                for name in tag_banks:
                    rows = [
                        (dict_id, str(r[0]), str(r[1] or ""), int(r[2] or 0) if isinstance(r[2], (int, float)) else 0,
                         str(r[3] or ""), int(r[4] or 0) if isinstance(r[4], (int, float)) else 0)
                        for r in json.loads(zf.read(name)) if isinstance(r, list) and len(r) >= 5
                    ]
                    conn.executemany("INSERT INTO tags(dict_id, name, category, ord, notes, score) VALUES (?, ?, ?, ?, ?, ?)", rows)
                for name in term_banks:
                    step += 1
                    progress(step / total_steps, f"Terms {step}/{len(term_banks)}")
                    rows = list(_term_rows(json.loads(zf.read(name)), dict_id, version))
                    conn.executemany(
                        "INSERT INTO terms(dict_id, expression, reading, def_tags, rules, score, glossary, sequence, term_tags)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
                    term_count += len(rows)
                for name in meta_banks:
                    step += 1
                    progress(step / total_steps, "Frequencies and pitch accents")
                    rows = [
                        (dict_id, str(r[0]), str(r[1]), json.dumps(r[2], ensure_ascii=False, separators=(",", ":")))
                        for r in json.loads(zf.read(name)) if isinstance(r, list) and len(r) >= 3
                    ]
                    conn.executemany("INSERT INTO term_meta(dict_id, expression, mode, data) VALUES (?, ?, ?, ?)", rows)
                    meta_count += len(rows)
                for name in kanji_banks:
                    step += 1
                    progress(step / total_steps, "Characters")
                    rows = list(_kanji_rows(json.loads(zf.read(name)), dict_id))
                    conn.executemany(
                        "INSERT INTO kanji(dict_id, character, onyomi, kunyomi, tags, meanings, stats) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
                    kanji_count += len(rows)
                for name in kanji_meta_banks:
                    rows = [
                        (dict_id, str(r[0]), str(r[1]), json.dumps(r[2], ensure_ascii=False, separators=(",", ":")))
                        for r in json.loads(zf.read(name)) if isinstance(r, list) and len(r) >= 3 and len(str(r[0])) == 1
                    ]
                    conn.executemany("INSERT INTO kanji_meta(dict_id, character, mode, data) VALUES (?, ?, ?, ?)", rows)
                    meta_count += len(rows)
                conn.execute("UPDATE dictionaries SET term_count = ?, meta_count = ?, kanji_count = ? WHERE id = ?",
                             (term_count, meta_count, kanji_count, dict_id))

            # Images used by structured-content glossaries.
            target = media_dir(dict_id)
            for name in zf.namelist():
                if Path(name).suffix.lower() in MEDIA_SUFFIXES:
                    dest = (target / name).resolve()
                    if not dest.is_relative_to(target.resolve()):
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
            progress(1.0, "Done")
        except Exception:
            delete_dictionary(dict_id)
            raise
    return get_dictionary(dict_id)


def _row(row) -> dict:
    return {key: row[key] for key in row.keys()}


def list_dictionaries() -> list[dict]:
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM dictionaries ORDER BY language, priority, id").fetchall()
    return [_row(r) for r in rows]


def get_dictionary(dict_id: int) -> dict:
    with db.session() as conn:
        row = conn.execute("SELECT * FROM dictionaries WHERE id = ?", (dict_id,)).fetchone()
    if row is None:
        raise DictionaryError("Unknown dictionary.")
    return _row(row)


def update_dictionary(dict_id: int, enabled: bool | None = None, language: str | None = None) -> dict:
    get_dictionary(dict_id)
    with db.session() as conn:
        if enabled is not None:
            conn.execute("UPDATE dictionaries SET enabled = ? WHERE id = ?", (1 if enabled else 0, dict_id))
        if language is not None:
            if language not in LANGUAGES:
                raise DictionaryError(f"Unsupported language: {language}")
            conn.execute("UPDATE dictionaries SET language = ? WHERE id = ?", (language, dict_id))
    return get_dictionary(dict_id)


def reorder(dict_ids: list[int]) -> None:
    with db.session() as conn:
        for position, dict_id in enumerate(dict_ids):
            conn.execute("UPDATE dictionaries SET priority = ? WHERE id = ?", (position, int(dict_id)))


def delete_dictionary(dict_id: int) -> None:
    with db.session() as conn:
        conn.execute("DELETE FROM terms WHERE dict_id = ?", (dict_id,))
        conn.execute("DELETE FROM term_meta WHERE dict_id = ?", (dict_id,))
        conn.execute("DELETE FROM tags WHERE dict_id = ?", (dict_id,))
        conn.execute("DELETE FROM kanji WHERE dict_id = ?", (dict_id,))
        conn.execute("DELETE FROM kanji_meta WHERE dict_id = ?", (dict_id,))
        conn.execute("DELETE FROM dictionaries WHERE id = ?", (dict_id,))
    shutil.rmtree(media_dir(dict_id), ignore_errors=True)


def media_path(dict_id: int, ref: str) -> Path:
    base = media_dir(dict_id).resolve()
    path = (base / ref).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise DictionaryError("No such image.")
    return path


# ---------------------------------------------------------------- background imports

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def start_import(path: Path, language: str, filename: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"id": job_id, "filename": filename, "progress": 0.0, "message": "Starting…",
                         "done": False, "error": None, "dictionary": None}

    def update(fraction, message):
        with _jobs_lock:
            _jobs[job_id].update(progress=round(fraction, 3), message=message)

    def run():
        try:
            result = import_dictionary(path, language, update)
            with _jobs_lock:
                _jobs[job_id].update(done=True, progress=1.0, message="Imported", dictionary=result)
        except Exception as exc:
            with _jobs_lock:
                _jobs[job_id].update(done=True, error=str(exc), message="Failed")
        finally:
            path.unlink(missing_ok=True)

    threading.Thread(target=run, daemon=True, name=f"dict-import-{job_id}").start()
    return job_id


def job_status(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
