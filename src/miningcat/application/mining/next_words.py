"""The next words to learn: the most frequent words of the language's frequency lists that the user doesn't have yet."""
import threading

from miningcat.application.mining import frequency, preferences
from miningcat.domain.dictionary.frequency_ranks import spellings
from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.sentence_readings.senses import senses_of, weight
from miningcat.domain.text.variants import text_variants
from miningcat.domain.words.forms import display_reading
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries
from miningcat.infrastructure.persistence.word_repository import WordRepository

DEFAULT_COUNT = 100
MAX_COUNT = 1000
_MEANING_SENSES = 3

_lock = threading.Lock()
_tracked_cache: dict[str, tuple[tuple, set[str]]] = {}  # language -> (key, _tracked())


def _tracked(language: str) -> set[str]:
    """The words that have a status (learning, known or ignored), lowercase, and for Chinese in both scripts too
    (a word known as 說 has 说), until one changes."""
    with database.session() as conn:
        repository = WordRepository(conn)
        key = (str(database.path), *repository.tracked_signature(language))
        with _lock:
            cached = _tracked_cache.get(language)
            if cached and cached[0] == key:
                return cached[1]
        expressions = repository.tracked_expressions(language)
    result = {w.lower() for w in spellings(language, *expressions)}
    with _lock:
        _tracked_cache[language] = (key, result)
    return result


def _entries(language: str, forms: list[str]) -> dict[str, dict]:
    """{form: {"headword", "reading", "meaning"}} from the enabled dictionaries: per word, the entry with the most
    senses that aren't a surname, a variant... (the first dictionary first when tied), found under the word as the
    reader would look it up (paris for Paris) or in the other script (a Simplified dictionary for 說)."""
    headwords = {form: list(dict.fromkeys(v for s in spellings(language, form) for v in text_variants(s, language)))
                 for form in forms}
    best: dict[str, tuple[int, str, list[str]]] = {}
    with database.session() as conn:
        rows = DictionaryQueries(conn).readings(language, [h for found in headwords.values() for h in found])
        for expression, reading, glossary in rows:
            found = senses_of(glossary)
            heaviest = weight(found)
            if expression not in best or heaviest > best[expression][0]:
                best[expression] = (heaviest, reading or "", found)
    result = {}
    for form, found in headwords.items():
        headword = next((h for h in found if h in best), None)
        if headword is not None:
            _, reading, meanings = best[headword]
            result[form] = {"headword": headword, "reading": reading,
                            "meaning": "; ".join(m.strip() for m in meanings[:_MEANING_SENSES])}
    return result


def next_words(language: str, count: int = DEFAULT_COUNT) -> dict:
    """{"frontier", "words": [{"rank", "expression", "reading", "meaning"}]}: the `count` most frequent words of the
    language's frequency lists (combined, as for the recommendations, in the script the user learns) that have no
    status yet: neither learning, known nor ignored. frontier is None without a frequency list."""
    count = max(1, min(int(count), MAX_COUNT))
    ranker = frequency.Ranker(language)
    if ranker.frontier is None:
        return {"frontier": None, "words": []}
    tracked = _tracked(language)
    chosen: list[str] = []
    seen: set[str] = set()
    for word in frequency.ordered(language, ranker.table):
        key = word.lower()
        if key in seen or key in tracked or not word.strip():
            continue
        seen.add(key)
        chosen.append(word)
        if len(chosen) >= count:
            break
    entries = _entries(language, chosen)
    system = preferences.reading_system(language)
    result = []
    for word in chosen:
        entry = entries.get(word, {})
        # saved as the reader saves it, under the dictionary's headword (cat for Cat), but in the script the user learns
        expression = entry.get("headword", word) if language not in CHINESE_LANGUAGES else word
        # display_reading also gives the reading of a Taigi word without one (from its Hanji)
        result.append({"rank": ranker.table[word], "expression": expression,
                       "reading": display_reading(language, expression, entry.get("reading", ""), system),
                       "meaning": entry.get("meaning", "")})
    return {"frontier": ranker.frontier, "words": result}
