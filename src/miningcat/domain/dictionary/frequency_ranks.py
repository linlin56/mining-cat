"""Ranks of words in a frequency list (term_meta "freq" rows of a dictionary)."""
import json
import re

from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.text.chinese_script import to_simplified, to_traditional

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


# A frequency of term_meta: 1234, "1234", {"value": 1234, "displayValue": "1234㋕"}, or {"reading": ..., "frequency": either}.
def _value(data) -> float | None:
    if isinstance(data, dict) and "frequency" in data:
        data = data["frequency"]
    if isinstance(data, dict):
        data = data.get("value")
    if isinstance(data, str):
        # some lists write their ranks as text ("12", like Yomitan, reading its first number)
        match = _NUMBER.search(data)
        data = float(match.group()) if match else None
    return data if isinstance(data, (int, float)) and not isinstance(data, bool) else None


def _variants(language: str, words: tuple[str, ...]) -> list[str]:
    found = [w for w in dict.fromkeys(words) if w]
    if language in CHINESE_LANGUAGES:
        # a list in one script still ranks the words of the other (説 / 说)
        found += [v for w in list(found) for v in (to_simplified(w, language), to_traditional(w, language)) if v not in found]
    return found


def rank_in(table: dict[str, int], language: str, *words: str) -> int | None:
    """Rank of a word in a list, from any of its spellings (dictionary headword, form saved by the user...)."""
    direct = [table[w] for w in words if w in table]
    if direct:
        return min(direct)
    found = [table[w] for w in _variants(language, words) if w in table]
    return min(found) if found else None



def ranks_from_rows(rows, occurrences: bool) -> dict[str, int]:
    """{expression: rank} of the (expression, data) rows of a frequency list, 1 being the most frequent word.
    `occurrences`: the values are counts (Yomitan's "occurrence-based" lists), not ranks."""
    values: dict[str, float] = {}
    for expression, data in rows:
        value = _value(json.loads(data))
        if value is None:
            continue
        best = values.get(expression)
        # a word with several readings keeps its most frequent one
        if best is None or (value > best if occurrences else value < best):
            values[expression] = value
    if occurrences:
        ordered = sorted(values, key=values.get, reverse=True)
        return {expression: i + 1 for i, expression in enumerate(ordered)}
    return {expression: max(1, int(value)) for expression, value in values.items()}


def _respelled(table: dict[str, int], spell) -> dict[str, int]:
    """The list with its words respelled (说 -> 說), a word written two ways keeping its best rank."""
    result: dict[str, int] = {}
    for word, rank in table.items():
        word = spell(word)
        result[word] = min(rank, result.get(word, rank))
    return result


def combine(tables: list[dict[str, int]], spell=None) -> dict[str, int]:
    """One list of several: a word ranks by its best rank in any of them, then by its average rank (a list without
    the word counting as its end), and the ranks are renumbered 1, 2, 3... so that the lists share one scale.
    `spell` writes the words of every list in one script first (a Simplified and a Traditional list: 说 is 說)."""
    if len(tables) == 1:
        return tables[0]
    if spell:
        tables = [_respelled(table, spell) for table in tables]
    words = {w for table in tables for w in table}

    def key(word: str):
        ranks = [table.get(word, len(table) + 1) for table in tables]
        return min(ranks), sum(ranks) / len(ranks), word

    return {word: i + 1 for i, word in enumerate(sorted(words, key=key))}
