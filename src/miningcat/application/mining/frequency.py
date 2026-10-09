import threading

from miningcat.domain.dictionary.frequency_ranks import rank_in, ranks_from_rows
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.persistence.word_repository import WordRepository

SETTING = "frequency_lists"  # {language: dictionary id}
# The recommended words are the first LIMIT_BASE of the list, and LIMIT_PER_KNOWN_WORD more per known word of it.
LIMIT_BASE = 1000
LIMIT_PER_KNOWN_WORD = 2


class _FrequencyCache:
    """The ranks of each frequency list, and the number of its words the user knows, until they change."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ranks: dict[int, tuple[tuple, dict[str, int]]] = {}    # dict id -> (key, {expression: rank})
        self.known: dict[str, tuple[tuple, int]] = {}               # language -> (key, words of the list known)

    def clear(self) -> None:
        with self.lock:
            self.ranks.clear()
            self.known.clear()


_cache = _FrequencyCache()


def lists(language: str) -> list[dict]:
    """The dictionaries of a language that have word frequencies, in the dictionary order."""
    with database.session() as conn:
        return DictionaryQueries(conn).frequency_lists(language)


def reference(language: str) -> dict | None:
    """The frequency list used for the language: the one chosen in the settings, else the first enabled one."""
    available = [d for d in lists(language) if d["enabled"]]
    chosen = (settings.get(SETTING, {}) or {}).get(language)
    return next((d for d in available if d["id"] == chosen), available[0] if available else None)


def choose(language: str, dict_id: int | None) -> None:
    if dict_id is not None and dict_id not in {d["id"] for d in lists(language)}:
        raise ValueError("This dictionary has no word frequencies.")
    chosen = dict(settings.get(SETTING, {}) or {})
    chosen[language] = dict_id
    settings.set(SETTING, chosen)


def ranks(dict_id: int, imported: float = 0) -> dict[str, int]:
    """{expression: rank} of a frequency list, 1 being the most frequent word."""
    key = (str(database.path), imported)
    with _cache.lock:
        cached = _cache.ranks.get(dict_id)
        if cached and cached[0] == key:
            return cached[1]
    with database.session() as conn:
        queries = DictionaryQueries(conn)
        result = ranks_from_rows(queries.frequencies_of_list(dict_id), queries.counts_occurrences(dict_id))
    with _cache.lock:
        _cache.ranks[dict_id] = (key, result)
    return result


def known_in_list(language: str, ref: dict, table: dict[str, int]) -> int:
    """How many words of the frequency list the user knows."""
    with database.session() as conn:
        repository = WordRepository(conn)
        key = (str(database.path), ref["id"], ref["imported"], *repository.known_signature(language))
        with _cache.lock:
            cached = _cache.known.get(language)
            if cached and cached[0] == key:
                return cached[1]
        expressions = repository.known_expressions(language)
    count = sum(1 for e in expressions if rank_in(table, language, e) is not None)
    with _cache.lock:
        _cache.known[language] = (key, count)
    return count


def _frontier(language: str, ref: dict, table: dict[str, int]) -> dict:
    known = known_in_list(language, ref, table)
    return {"dictionary": {"id": ref["id"], "title": ref["title"]}, "known": known, "words": len(table),
            "limit": LIMIT_BASE + LIMIT_PER_KNOWN_WORD * known}


def frontier(language: str) -> dict | None:
    """{"dictionary", "known", "words", "limit"} of the language's frequency list, or None when it has none."""
    return Ranker(language).frontier


class Ranker:
    """Ranks of many words in the language's frequency list, and its limit (frontier None without a list)."""

    def __init__(self, language: str):
        self.language = language
        ref = reference(language)
        self.table = ranks(ref["id"], ref["imported"]) if ref else {}
        self.frontier = _frontier(language, ref, self.table) if ref else None

    def rank(self, *words: str) -> int | None:
        return rank_in(self.table, self.language, *words) if self.table else None

    def frequent(self, *words: str) -> bool:
        """Whether a word is frequent enough to be recommended (any word, without a frequency list)."""
        if self.frontier is None:
            return True
        rank = self.rank(*words)
        return rank is not None and rank <= self.frontier["limit"]


def clear_cache() -> None:
    _cache.clear()
