import json
import re
from pathlib import Path

from miningcat.domain.dictionary.errors import DictionaryError

FREQUENCY_LIST_SUFFIXES = (".json", ".txt", ".csv", ".tsv")


def is_frequency_list(path: Path) -> bool:
    return path.suffix.lower() in FREQUENCY_LIST_SUFFIXES


def read_frequency_list(path: Path) -> list[tuple[str, str]]:
    """(word, reading) of a JSON frequency list or a text list, most frequent first."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise DictionaryError("A frequency list must be a UTF-8 text or JSON file.")
    entries = _json_entries(text) if path.suffix.lower() == ".json" else _text_entries(text)
    entries = [(w, r) for w, r in entries if w]
    if not entries:
        raise DictionaryError("This frequency list has no words.")
    return entries


def _json_entries(text: str) -> list[tuple[str, str]]:
    try:
        data = json.loads(text)
    except ValueError:
        raise DictionaryError("This file isn't valid JSON.")
    if isinstance(data, dict):  # {"words": [...]} or a similar wrapper
        data = next((v for v in data.values() if isinstance(v, list)), [])
    if not isinstance(data, list):
        raise DictionaryError("A JSON frequency list is an array of words, most frequent first.")
    entries = []
    for item in data:
        if isinstance(item, list) and item:
            entries.append((str(item[0]).strip(), str(item[1]).strip() if len(item) > 1 and item[1] else ""))
        elif isinstance(item, str):
            entries.append((item.strip(), ""))
    return entries


def _text_entries(text: str) -> list[tuple[str, str]]:
    entries = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = re.split(r"[\t,;]", line.strip())
        entries.append((parts[0].strip(), parts[1].strip() if len(parts) > 1 and not parts[1].strip().isdigit() else ""))
    return entries
