import json
import re
import zipfile
from pathlib import Path

from miningcat.domain.dictionary.errors import DictionaryError

MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif", ".tif", ".tiff"}
# Rows read from a bank to guess the language of a dictionary.
SAMPLE_ROWS = 2000


def _json(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class YomitanArchive:
    """A Yomitan dictionary: a zip of index.json and JSON banks of terms, frequencies, characters and tags.
    The rows of each bank are given as the tuples the database stores."""

    def __init__(self, zf: zipfile.ZipFile):
        self._zf = zf
        self.index = self._read_index()

    @classmethod
    def open(cls, path: Path) -> "YomitanArchive":
        try:
            return cls(zipfile.ZipFile(path))
        except zipfile.BadZipFile:
            raise DictionaryError("This file isn't a zip archive.")

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "YomitanArchive":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def title(self) -> str:
        return self.index["title"]

    @property
    def revision(self) -> str:
        return str(self.index.get("revision", ""))

    @property
    def version(self) -> int:
        return int(self.index.get("format", self.index.get("version", 3)) or 3)

    def banks(self, prefix: str) -> list[str]:
        """The bank files of a kind (term_bank, term_meta_bank, kanji_bank...), in their order."""
        pattern = re.compile(rf"^(?:.*/)?{prefix}_(\d+)\.json$")
        found = [(int(m.group(1)), name) for name in self._zf.namelist() if (m := pattern.match(name))]
        return [name for _, name in sorted(found)]

    def rows(self, bank: str) -> list:
        return json.loads(self._zf.read(bank))

    def samples(self) -> list[tuple[str, str]]:
        """(expression, reading) samples telling the language of the headwords."""
        samples = []
        banks = self.banks("term_bank")
        if banks:
            for row in self.rows(banks[0])[:SAMPLE_ROWS]:
                if isinstance(row, list) and len(row) >= 2:
                    samples.append((str(row[0]), str(row[1])))
        meta_banks = self.banks("term_meta_bank")
        if not samples and meta_banks:
            for row in self.rows(meta_banks[0])[:SAMPLE_ROWS]:
                if isinstance(row, list) and row:
                    samples.append((str(row[0]), ""))
        kanji_banks = self.banks("kanji_bank")
        if not samples and kanji_banks:
            # the readings tell the language: on'yomi in katakana for Japanese, pinyin for Chinese
            for row in self.rows(kanji_banks[0])[:SAMPLE_ROWS]:
                if isinstance(row, list) and len(row) >= 3:
                    samples.append((str(row[0]), f"{row[1]} {row[2]}"))
        return samples

    def term_rows(self, bank: str, dict_id: int):
        version = self.version
        for row in self.rows(bank):
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
            yield dict_id, expression, reading, def_tags, rules, score, _json(glossary), sequence, term_tags

    def meta_rows(self, bank: str, dict_id: int) -> list[tuple]:
        """Frequencies, pitch accents and IPA of words."""
        return [(dict_id, str(r[0]), str(r[1]), _json(r[2])) for r in self.rows(bank) if isinstance(r, list) and len(r) >= 3]

    # Only single characters are kept: some dictionaries (CC-CEDICT Hanzi) also put whole words in their kanji banks.
    def kanji_rows(self, bank: str, dict_id: int):
        for row in self.rows(bank):
            if not isinstance(row, list) or len(row) < 5 or len(str(row[0])) != 1:
                continue
            meanings = [str(m) for m in row[4]] if isinstance(row[4], list) else [str(row[4])]
            stats = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
            yield (dict_id, str(row[0]), str(row[1] or ""), str(row[2] or ""), str(row[3] or ""),
                   json.dumps(meanings, ensure_ascii=False), json.dumps(stats, ensure_ascii=False))

    def kanji_meta_rows(self, bank: str, dict_id: int) -> list[tuple]:
        return [(dict_id, str(r[0]), str(r[1]), _json(r[2]))
                for r in self.rows(bank) if isinstance(r, list) and len(r) >= 3 and len(str(r[0])) == 1]

    def tag_rows(self, bank: str, dict_id: int) -> list[tuple]:
        return [
            (dict_id, str(r[0]), str(r[1] or ""), int(r[2] or 0) if isinstance(r[2], (int, float)) else 0,
             str(r[3] or ""), int(r[4] or 0) if isinstance(r[4], (int, float)) else 0)
            for r in self.rows(bank) if isinstance(r, list) and len(r) >= 5
        ]

    def extract_media(self, target: Path) -> None:
        """Copies the images used by structured-content glossaries to `target`."""
        for name in self._zf.namelist():
            if Path(name).suffix.lower() in MEDIA_SUFFIXES:
                dest = (target / name).resolve()
                if not dest.is_relative_to(target.resolve()):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self._zf.read(name))

    def _read_index(self) -> dict:
        index_name = next((n for n in self._zf.namelist() if n.rsplit("/", 1)[-1] == "index.json"), None)
        if index_name is None:
            raise DictionaryError("This zip has no index.json: it isn't a Yomitan dictionary.")
        try:
            index = json.loads(self._zf.read(index_name))
        except ValueError:
            raise DictionaryError("The dictionary's index.json is not valid JSON.")
        if not isinstance(index, dict) or not index.get("title"):
            raise DictionaryError("The dictionary's index.json has no title.")
        return index
