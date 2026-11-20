"""MiningCat's own list of the Taiwan reading of Mandarin words (時候 shí hòu, 垃圾 lè sè), written by hand: no
dictionary's data. With "Force Taiwanese pronunciation", a word of the list is read this way whatever the
dictionaries say.

taiwan_readings.csv: one word per line and its Taiwan reading in numbered pinyin (shi2 hou4; tone marks or zhuyin work too), shown
in pinyin or zhuyin as the user chose."""
import csv
from functools import cache
from pathlib import Path

from zhuyin_converter import numbered_pinyin

READINGS_FILE = Path(__file__).parent / "taiwan_readings.csv"


@cache
def _readings() -> dict[str, str]:
    with READINGS_FILE.open(encoding="utf-8", newline="") as f:
        return {row["word"].strip(): numbered_pinyin(row["taiwan"]) for row in csv.DictReader(f) if row["word"].strip()}


def taiwan_reading(word: str) -> str:
    """The Taiwan reading of a word of the list in numbered pinyin (shi2 hou4), "" for the other words."""
    return _readings().get(word, "")


def all_readings() -> dict[str, str]:
    """{word: numbered pinyin} of the whole list."""
    return dict(_readings())
