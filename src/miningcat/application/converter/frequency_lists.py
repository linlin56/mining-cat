import json
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.frequency_lists import character_list, word_frequency
from miningcat.domain.languages import Language


@dataclass
class SavedList:
    path: Path
    # Shown to the user, and written in the log.
    message: str
    log: str


class FrequencyListMaker(ABC):
    """A kind of frequency list, made from a text and saved to output/frequency."""

    label: str

    def supports(self, language: Language) -> bool:
        return True

    @abstractmethod
    def make(self, text: str, language: Language, name: str) -> SavedList:
        """Computes the list of a text and saves it, named after `name` (the book or the video)."""


class WordFrequencyList(FrequencyListMaker):
    """A CSV of the words and their number of occurrences, most frequent first."""

    label = "Word frequency"

    def make(self, text: str, language: Language, name: str) -> SavedList:
        counter = word_frequency.compute(text, language)
        path = paths.frequency / f"{name}_word_freq.csv"
        save_csv(counter, path)
        total = word_frequency.total_count(counter)
        return SavedList(path, f"Word frequency saved ({len(counter)} unique words, {total} total words).",
                         f"Word frequency: {len(counter)} unique words, {total} total words : {path}")


class CharacterFrequencyList(FrequencyListMaker):
    """A Kanji Grid character list (JSON)."""

    label = "Character list"

    def supports(self, language: Language) -> bool:
        return character_list.supports_language(language)

    def make(self, text: str, language: Language, name: str) -> SavedList:
        counter = character_list.compute(text, language)
        path = paths.frequency / f"{name}_char_list.json"
        save_json(character_list.build_json(name, language, counter), path)
        return SavedList(path, f"Character list saved ({len(counter)} unique characters).",
                         f"Character list: {len(counter)} unique characters → {path}")


MAKERS: dict[str, FrequencyListMaker] = {"word": WordFrequencyList(), "char": CharacterFrequencyList()}


def save_csv(counter: Counter, output_path: Path, min_count: int = 1) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("word,count\n")
        for word, count in counter.most_common():
            if count >= min_count:
                f.write(f"{word},{count}\n")


def save_json(data: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
