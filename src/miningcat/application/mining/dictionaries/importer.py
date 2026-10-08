import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from miningcat.application.mining.dictionaries.catalog import delete_dictionary, get_dictionary
from miningcat.config.paths import paths
from miningcat.domain.dictionary.errors import DictionaryError
from miningcat.domain.dictionary.language_guess import guess_dictionary_language
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.dictionaries.frequency_list_file import is_frequency_list, read_frequency_list
from miningcat.infrastructure.dictionaries.yomitan_archive import YomitanArchive
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_repository import DictionaryRepository

# progress(fraction, message), called along an import.
Progress = Callable[[float, str], None]


def _no_progress(fraction: float, message: str) -> None:
    pass


class DictionaryImporter(ABC):
    """Imports one kind of dictionary file into the database."""

    def __init__(self, path: Path, filename: str = ""):
        self.path = path
        self.filename = filename

    @abstractmethod
    def inspect(self) -> dict:
        """{"title", "revision", "language", "has_terms", "has_meta", "has_kanji"}, without importing anything.
        The language is guessed from the headwords ("" when unsure)."""

    @abstractmethod
    def import_into(self, language: str, progress: Progress) -> int:
        """Imports the file for `language`. Returns the id of the new dictionary."""

    def run(self, language: str = "", progress: Progress | None = None) -> int:
        language = language or self.inspect()["language"]
        if not language:
            raise DictionaryError(self._unknown_language_message)
        if language not in LANGUAGES:
            raise DictionaryError(f"Unsupported language: {language}")
        return self.import_into(language, progress or _no_progress)

    _unknown_language_message = "Couldn't tell which language this dictionary is for: pick it in the list."


class FrequencyListImporter(DictionaryImporter):
    """A JSON or plain text list of words, most frequent first: each word gets its rank."""

    _unknown_language_message = "Couldn't tell which language this frequency list is for."

    @property
    def title(self) -> str:
        return Path(self.filename or self.path.name).stem

    def inspect(self) -> dict:
        entries = read_frequency_list(self.path)
        return {
            "title": self.title, "revision": "", "has_terms": False, "has_meta": True, "has_kanji": False,
            "language": guess_dictionary_language(entries[:2000]),
        }

    def import_into(self, language: str, progress: Progress) -> int:
        rows, seen = [], set()
        for rank, (word, reading) in enumerate(read_frequency_list(self.path), start=1):
            if (word, reading) in seen:
                continue
            seen.add((word, reading))
            data = {"reading": reading, "frequency": rank} if reading else rank
            rows.append((word, "freq", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
        with database.session() as conn:
            repository = DictionaryRepository(conn)
            if repository.exists(self.title, ""):
                raise DictionaryError(f"“{self.title}” is already imported.")
            dict_id = repository.add(title=self.title, revision="", language=language, freq_mode="rank-based",
                                     meta_count=len(rows))
            progress(0.5, f"{len(rows)} words")
            repository.add_term_meta([(dict_id, *row) for row in rows])
        progress(1.0, "Done")
        return dict_id


class YomitanImporter(DictionaryImporter):
    """A Yomitan dictionary zip: terms, frequencies and pitch accents, characters, tags and images."""

    def inspect(self) -> dict:
        with YomitanArchive.open(self.path) as archive:
            source_language = archive.index.get("sourceLanguage")
            return {
                "title": archive.title,
                "revision": archive.revision,
                "language": source_language if source_language else guess_dictionary_language(archive.samples()),
                "has_terms": bool(archive.banks("term_bank")),
                "has_meta": bool(archive.banks("term_meta_bank")),
                "has_kanji": bool(archive.banks("kanji_bank")),
            }

    def import_into(self, language: str, progress: Progress) -> int:
        with YomitanArchive.open(self.path) as archive:
            term_banks = archive.banks("term_bank")
            meta_banks = archive.banks("term_meta_bank")
            kanji_banks = archive.banks("kanji_bank")
            kanji_meta_banks = archive.banks("kanji_meta_bank")
            if not term_banks and not meta_banks and not kanji_banks and not kanji_meta_banks:
                raise DictionaryError("This dictionary has no terms, characters or frequency data.")
            dict_id = self._add_dictionary(archive, language)
            try:
                self._import_banks(archive, dict_id, progress)
                archive.extract_media(paths.dictionary_media(dict_id))
                progress(1.0, "Done")
            except Exception:
                delete_dictionary(dict_id)
                raise
        return dict_id

    @staticmethod
    def _add_dictionary(archive: YomitanArchive, language: str) -> int:
        index = archive.index
        with database.session() as conn:
            repository = DictionaryRepository(conn)
            if repository.exists(archive.title, archive.revision):
                raise DictionaryError(f"“{archive.title}” is already imported.")
            return repository.add(
                title=archive.title, revision=archive.revision, language=language,
                target_language=index.get("targetLanguage"), author=index.get("author"), url=index.get("url"),
                description=index.get("description"), attribution=index.get("attribution"),
                freq_mode=str(index.get("frequencyMode") or ""),
            )

    @staticmethod
    def _import_banks(archive: YomitanArchive, dict_id: int, progress: Progress) -> None:
        term_banks = archive.banks("term_bank")
        meta_banks = archive.banks("term_meta_bank")
        kanji_banks = archive.banks("kanji_bank")
        total_steps = max(1, len(term_banks) + len(meta_banks) + len(kanji_banks) + 1)
        step = 0
        term_count = meta_count = kanji_count = 0
        with database.session() as conn:
            repository = DictionaryRepository(conn)
            for bank in archive.banks("tag_bank"):
                repository.add_tags(archive.tag_rows(bank, dict_id))
            for bank in term_banks:
                step += 1
                progress(step / total_steps, f"Terms {step}/{len(term_banks)}")
                rows = list(archive.term_rows(bank, dict_id))
                repository.add_terms(rows)
                term_count += len(rows)
            for bank in meta_banks:
                step += 1
                progress(step / total_steps, "Frequencies and pitch accents")
                rows = archive.meta_rows(bank, dict_id)
                repository.add_term_meta(rows)
                meta_count += len(rows)
            for bank in kanji_banks:
                step += 1
                progress(step / total_steps, "Characters")
                rows = list(archive.kanji_rows(bank, dict_id))
                repository.add_kanji(rows)
                kanji_count += len(rows)
            for bank in archive.banks("kanji_meta_bank"):
                rows = archive.kanji_meta_rows(bank, dict_id)
                repository.add_kanji_meta(rows)
                meta_count += len(rows)
            repository.set_counts(dict_id, term_count, meta_count, kanji_count)


def importer_for(path: Path, filename: str = "") -> DictionaryImporter:
    """The importer of a file: frequency lists are recognised by their extension, the rest is a Yomitan zip."""
    return FrequencyListImporter(path, filename) if is_frequency_list(path) else YomitanImporter(path, filename)


def inspect(path: Path, filename: str = "") -> dict:
    """Title and guessed language of a dictionary zip (or a frequency list), without importing it."""
    return importer_for(path, filename).inspect()


def import_dictionary(path: Path, language: str = "", progress: Progress | None = None, filename: str = "") -> dict:
    """Imports a dictionary zip, or a frequency list. `progress(fraction, message)` is called along the way."""
    return get_dictionary(importer_for(path, filename).run(language, progress))
