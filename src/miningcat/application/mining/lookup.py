import json
import re

from miningcat.application.mining import preferences, words
from miningcat.domain.dictionary import glossary
from miningcat.domain.dictionary.definitions import merge_definitions, move_other_readings, readable
from miningcat.domain.dictionary.deinflection import Deinflection, LanguageTransformer, transformer_for
from miningcat.domain.languages import CHINESE_LANGUAGES, is_no_space
from miningcat.domain.text import taigi
from miningcat.domain.text.chinese_script import chinese_counterpart, chinese_script
from miningcat.domain.text.readings import reading_key
from miningcat.domain.text.scripts import HAN_CHARACTER
from miningcat.domain.text.variants import text_variants
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries

MAX_SCAN = 20          # characters tried from the cursor in languages without spaces
MAX_WORDS = 5          # words tried from the cursor in other languages
MAX_RESULTS = 12
STRICT_PART_OF_SPEECH = {"ja", "ko"}

_WORD_END = re.compile(r"[\w’'\-]+", re.UNICODE)
# Romanized Taigi: words with their tone marks (tsia̍h-pn̄g, POJ's o͘ and ⁿ).
_TAIGI_WORD_END = re.compile(r"[\w\u0300-\u036f’'\-]+", re.UNICODE)


def _sources(text: str, language: str) -> list[str]:
    """Candidate texts starting at the cursor, longest first."""
    text = text.strip("\n")
    romanized = language == "nan" and bool(re.match(r"[A-Za-z\u00c0-\u024f\u1e00-\u1eff]", text))
    if is_no_space(language) and not romanized:
        text = text[:MAX_SCAN]
        return [text[:n] for n in range(len(text), 0, -1) if text[:n].strip()]
    ends = []
    for m in (_TAIGI_WORD_END if romanized else _WORD_END).finditer(text):
        ends.append(m.end())
        if len(ends) >= MAX_WORDS:
            break
    candidates = [text[:end].rstrip("-’'") for end in reversed(ends)]
    # Korean words carry their particles and endings (친구와): the start of the word is a word too.
    if language == "ko" and ends:
        candidates += [text[:end] for end in range(ends[0] - 1, 0, -1)]
    return [c for c in dict.fromkeys(candidates) if c]


def _convert_senses(entries: list[dict], language: str) -> None:
    """The split senses and their examples in the script the user learns (DrEye's examples are in Simplified)."""
    preference = preferences.chinese_script_preference(language)

    def convert(sense: dict) -> None:
        if "text" in sense:
            sense["text"] = words.preferred_form(language, sense["text"], preference)
        for example in sense.get("examples", ()):
            example["text"] = words.preferred_form(language, example["text"], preference)
        for sub in sense.get("subs", ()):
            convert(sub)

    for g in entries:
        for definition in g["definitions"]:
            for item in definition["glossary"]:
                if isinstance(item, dict) and item.get("type") == "senses":
                    for sense in item["senses"]:
                        convert(sense)
                    for example in item["examples"]:
                        convert(example)


def _taigi_readings(entries: list[dict]) -> None:
    """Taigi dictionaries in Hanji only (no reading): taibun's Tâi-lô reading."""
    for g in entries:
        if not g["reading"] or g["reading"] == g["expression"]:
            g["reading"] = taigi.reading(g["expression"]) or g["reading"]


class DictionaryLookup:
    """The entries of the enabled dictionaries for the text at the cursor, longest match first: every spelling
    and deinflection of the candidate texts is looked up, then the rows are grouped by headword and pronunciation,
    ranked, and completed with frequencies, pronunciations, characters and the word's status."""

    def __init__(self, language: str, text: str):
        self.language = language
        self.text = text
        self.transformer: LanguageTransformer | None = transformer_for(language)

    def run(self) -> dict:
        sources = _sources(self.text, self.language)
        if not sources:
            return self._result([], 0)
        candidates = self._candidates(sources)
        with database.session() as conn:
            queries = DictionaryQueries(conn)
            dicts = queries.enabled_dictionaries(self.language)
            if not dicts:
                return self._result([], 0)
            groups = self._group(self._best_matches(queries, dicts, candidates), dicts)
            if self.language in CHINESE_LANGUAGES:
                move_other_readings(groups, self.language)
            self._add_frequencies_and_pronunciations(queries, dicts, groups)
            ordered = self._order(groups)
            self._finish_definitions(queries, ordered)
            self._add_characters(queries, dicts, ordered)
        if self.language in CHINESE_LANGUAGES:
            _convert_senses(ordered, self.language)
        if self.language == "nan":
            _taigi_readings(ordered)
        self._add_statuses(ordered)
        return self._result(ordered, len(dicts))

    def _result(self, entries: list[dict], dictionaries: int) -> dict:
        return {"entries": entries, "dictionaries": dictionaries, "language": self.language}

    def _candidates(self, sources: list[str]) -> dict[str, list[tuple[str, Deinflection]]]:
        """deinflected text -> [(source text, deinflection)]"""
        candidates: dict[str, list[tuple[str, Deinflection]]] = {}
        for source in sources:
            for variant in text_variants(source, self.language):
                deinflections = self.transformer.transform(variant) if self.transformer else [Deinflection(variant, 0, ())]
                for d in deinflections:
                    candidates.setdefault(d.text, []).append((source, d))
        return candidates

    def _best_matches(self, queries: DictionaryQueries, dicts: dict[int, dict], candidates: dict) -> dict[int, tuple]:
        """The best match of each dictionary row: {row id: (rank, source, deinflection, row)}."""
        transformer = self.transformer
        matches: dict[int, tuple] = {}
        # Japanese and Korean dictionaries always give parts of speech, so a deinflected form must fit
        # them (like Yomitan). Other dictionaries often don't: an entry without any is accepted.
        strict = self.language in STRICT_PART_OF_SPEECH
        for row in queries.terms(list(dicts), list(candidates)):
            pos_flags = transformer.flags_for_parts_of_speech(row["rules"].split()) if transformer else 0
            for key in (row["expression"], row["reading"]):
                for source, d in candidates.get(key, ()):
                    if transformer and not transformer.conditions_match(d.conditions, pos_flags):
                        if strict or row["rules"].strip():
                            continue
                    rank = (len(source), -len(d.trace), key == row["expression"])
                    best = matches.get(row["id"])
                    if best is None or rank > best[0]:
                        matches[row["id"]] = (rank, source, d, row)
        return matches

    def _group(self, matches: dict[int, tuple], dicts: dict[int, dict]) -> dict[tuple, dict]:
        """The rows of every dictionary grouped by headword and pronunciation: 行 xíng and 行 háng are two entries,
        行 xíng from two dictionaries (or two rows of one) is one, whether written xíng or xing2."""
        transformer = self.transformer
        groups: dict[tuple, dict] = {}
        for rank, source, d, row in matches.values():
            reading = (row["reading"] or row["expression"]).replace("\u0261", "g")  # 兩岸詞典 writes xínɡ
            key = (row["expression"], reading_key(reading, self.language))
            group = groups.get(key)
            if group is None or rank > group["rank"]:
                kept = group["definitions"] if group else []
                if group and readable(group["reading"], reading):
                    reading = group["reading"]
                group = {
                    "rank": rank, "expression": row["expression"], "reading": reading,
                    "source": source, "length": len(source),
                    "inflections": transformer.describe(tuple(reversed(d.trace))) if transformer and d.trace else [],
                    "definitions": kept, "score": row["score"],
                }
                groups[key] = group
            elif readable(reading, group["reading"]):
                group["reading"] = reading
            dictionary = dicts[row["dict_id"]]
            group["definitions"].append({
                "dictionary": dictionary["title"], "dict_id": dictionary["id"], "priority": dictionary["priority"],
                "tags": [t for t in row["def_tags"].split() if t], "term_tags": [t for t in row["term_tags"].split() if t],
                "glossary": glossary.structure(json.loads(row["glossary"]), row["expression"]), "score": row["score"],
                "sequence": row["sequence"], "row": row["id"],
            })
            group["score"] = max(group["score"], row["score"])
        return groups

    def _same_reading(self, item: dict, group: dict) -> bool:
        return not item["reading"] or reading_key(item["reading"], self.language) == reading_key(group["reading"], self.language)

    def _add_frequencies_and_pronunciations(self, queries: DictionaryQueries, dicts: dict[int, dict],
                                            groups: dict[tuple, dict]) -> None:
        expressions = list({g["expression"] for g in groups.values()})
        freqs = queries.frequencies(dicts, expressions)
        sounds = queries.pronunciations(dicts, expressions)
        for g in groups.values():
            g["frequencies"] = [
                f for f in sorted(freqs.get(g["expression"], []), key=lambda f: f["priority"]) if self._same_reading(f, g)
            ]
            g["pronunciations"] = [
                {k: v for k, v in p.items() if k != "priority"}
                for p in sorted(sounds.get(g["expression"], []), key=lambda p: p["priority"]) if self._same_reading(p, g)
            ]
            # rank in the first frequency list that has the word (smaller = more frequent)
            g["frequency_rank"] = next((f["value"] for f in g["frequencies"] if isinstance(f["value"], (int, float))),
                                       float("inf"))

    @staticmethod
    def _order(groups: dict[tuple, dict]) -> list[dict]:
        """Longest match first, then the least inflected, the headword over the reading, the most frequent, the
        first dictionary, the best score."""
        return sorted(
            groups.values(),
            key=lambda g: (-g["rank"][0], -g["rank"][1], not g["rank"][2], g["frequency_rank"],
                           min(x["priority"] for x in g["definitions"]), -g["score"]),
        )[:MAX_RESULTS]

    @staticmethod
    def _finish_definitions(queries: DictionaryQueries, ordered: list[dict]) -> None:
        """Definitions in the dictionaries' order, without repeats, with the notes of their tags."""
        tag_cache: dict[int, dict] = {}
        for g in ordered:
            g["definitions"].sort(key=lambda x: (x["priority"], x["row"]))  # senses keep the dictionary's order
            g["definitions"] = merge_definitions(g["definitions"])
            for definition in g["definitions"]:
                names = set(definition["tags"]) | set(definition["term_tags"])
                notes = queries.tag_notes(definition["dict_id"], names - set(tag_cache.get(definition["dict_id"], {})))
                tag_cache.setdefault(definition["dict_id"], {}).update(notes)
                definition["tag_info"] = {n: tag_cache[definition["dict_id"]].get(n, {}) for n in names}
            del g["rank"]
            del g["frequency_rank"]

    @staticmethod
    def _add_characters(queries: DictionaryQueries, dicts: dict[int, dict], ordered: list[dict]) -> None:
        found = queries.characters(dicts, [g["expression"] for g in ordered])
        for g in ordered:
            g["characters"] = [{"character": c, "entries": found[c]}
                               for c in dict.fromkeys(HAN_CHARACTER.findall(g["expression"])) if c in found]

    def _add_statuses(self, ordered: list[dict]) -> None:
        """The form the word is saved under, its status, and for Chinese its script and its other form."""
        language = self.language
        for g in ordered:
            form = words.preferred_form(language, g["expression"])
            g["form"] = form
            g["status"] = words.status_of(language, form, g["reading"])
            if language in CHINESE_LANGUAGES:
                g["script"] = chinese_script(g["expression"])
                other = chinese_counterpart(g["expression"], language)
                g["counterpart"] = {"script": other[0], "expression": other[1]} if other else None


def lookup(language: str, text: str) -> dict:
    """Entries for `text` (the text from the cursor onwards), longest match first."""
    return DictionaryLookup(language, text).run()
