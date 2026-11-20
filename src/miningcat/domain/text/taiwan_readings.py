"""MiningCat's own list of the Taiwan reading of Mandarin words (時候 shí hòu, 垃圾 lè sè). With "Force Taiwanese
pronunciation", a word of the list is read this way whatever the dictionaries say.

taiwan_readings.toml: sections grouping the words (days of the week, 期 qi2…), one "word" = "reading" per line, the
reading in numbered pinyin (tone marks or zhuyin work too), shown in pinyin or zhuyin as the user chose."""
import tomllib
from functools import cache
from pathlib import Path

from zhuyin_converter import numbered_pinyin

READINGS_FILE = Path(__file__).parent / "taiwan_readings.toml"


def parse(text: str) -> dict[str, str]:
    """{word: numbered pinyin} of the list's TOML. A word listed twice, or whose reading can't be read, is an error."""
    readings: dict[str, str] = {}
    for name, section in tomllib.loads(text).items():
        if not isinstance(section, dict):
            raise ValueError(f"{name}: words go in a section")
        for word, reading in section.items():
            if word in readings:
                raise ValueError(f"{word} is listed twice")
            pinyin = numbered_pinyin(str(reading))
            if not pinyin:
                raise ValueError(f"{word}: {reading!r} isn't a reading")
            readings[word] = pinyin
    return readings


@cache
def _readings() -> dict[str, str]:
    return parse(READINGS_FILE.read_text(encoding="utf-8"))


def taiwan_reading(word: str) -> str:
    """The Taiwan reading of a word of the list in numbered pinyin (shi2 hou4), "" for the other words."""
    return _readings().get(word, "")


def all_readings() -> dict[str, str]:
    """{word: numbered pinyin} of the whole list."""
    return dict(_readings())
