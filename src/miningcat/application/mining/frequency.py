import threading

from miningcat.domain.dictionary.frequency_ranks import combine, rank_in, ranks_from_rows
from miningcat.application.mining import preferences
from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.words.forms import preferred_form
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.persistence.word_repository import WordRepository

SETTING = "frequency_lists"  # {language: [dictionary ids]} (a single id before lists could be combined)
# The recommended words are the first LIMIT_BASE of the list, and LIMIT_PER_KNOWN_WORD more per known word of it.
LIMIT_BASE = 1000
LIMIT_PER_KNOWN_WORD = 2


class _FrequencyCache:
    """The ranks of each frequency list, and the number of its words the user knows, until they change."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ranks: dict[int, tuple[tuple, dict[str, int]]] = {}    # dict id -> (key, {expression: rank})
        self.combined: dict[str, tuple[tuple, dict[str, int]]] = {}  # language -> (key, ranks of its lists combined)
        self.known: dict[str, tuple[tuple, int]] = {}               # language -> (key, words of the lists known)

    def clear(self) -> None:
        with self.lock:
            self.ranks.clear()
            self.combined.clear()
            self.known.clear()


_cache = _FrequencyCache()


def lists(language: str) -> list[dict]:
    """The dictionaries of a language that have word frequencies, in the dictionary order."""
    with database.session() as conn:
        return DictionaryQueries(conn).frequency_lists(language)


def _chosen_ids(language: str) -> list[int] | None:
    """The lists chosen in the settings (None: never chosen)."""
    chosen = (settings.get(SETTING, {}) or {}).get(language)
    if chosen is None:
        return None
    return [chosen] if isinstance(chosen, int) else [i for i in chosen if isinstance(i, int)]


def references(language: str) -> list[dict]:
    """The enabled frequency lists used for the language, combined: the ones chosen in the settings, else the first one
    (none when the user unticked them all)."""
    available = [d for d in lists(language) if d["enabled"]]
    chosen = _chosen_ids(language)
    if chosen is None:
        return available[:1]
    return [d for d in available if d["id"] in chosen]


def choose(language: str, dict_ids: list[int]) -> None:
    unknown = set(dict_ids) - {d["id"] for d in lists(language)}
    if unknown:
        raise ValueError("This dictionary has no word frequencies.")
    chosen = dict(settings.get(SETTING, {}) or {})
    chosen[language] = list(dict.fromkeys(dict_ids))
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


def _lists_key(refs: list[dict]) -> tuple:
    return (str(database.path), *((ref["id"], ref["imported"]) for ref in refs))


def _script(language: str) -> str | None:
    """For Chinese, the script the lists are written in once combined: the one the user learns (Traditional when both),
    so that a Simplified and a Traditional list share their words."""
    if language not in CHINESE_LANGUAGES:
        return None
    preference = preferences.chinese_script_preference(language)
    return preference if preference in ("traditional", "simplified") else "traditional"


def combined_ranks(language: str, refs: list[dict]) -> dict[str, int]:
    """{expression: rank} of the lists used for a language, combined into one (see frequency_ranks.combine)."""
    script = _script(language)
    key = (*_lists_key(refs), script)
    with _cache.lock:
        cached = _cache.combined.get(language)
        if cached and cached[0] == key:
            return cached[1]
    spell = (lambda word: preferred_form(language, word, script)) if script else None
    result = combine([ranks(ref["id"], ref["imported"]) for ref in refs], spell)
    with _cache.lock:
        _cache.combined[language] = (key, result)
    return result


def known_in_list(language: str, refs: list[dict], table: dict[str, int]) -> int:
    """How many words of the frequency lists the user knows."""
    with database.session() as conn:
        repository = WordRepository(conn)
        key = (*_lists_key(refs), _script(language), *repository.known_signature(language))
        with _cache.lock:
            cached = _cache.known.get(language)
            if cached and cached[0] == key:
                return cached[1]
        expressions = repository.known_expressions(language)
    count = sum(1 for e in expressions if rank_in(table, language, e) is not None)
    with _cache.lock:
        _cache.known[language] = (key, count)
    return count


def _frontier(language: str, refs: list[dict], table: dict[str, int]) -> dict:
    known = known_in_list(language, refs, table)
    return {"dictionaries": [{"id": ref["id"], "title": ref["title"]} for ref in refs],
            "title": " + ".join(ref["title"] for ref in refs), "known": known, "words": len(table),
            "limit": LIMIT_BASE + LIMIT_PER_KNOWN_WORD * known}


def frontier(language: str) -> dict | None:
    """{"dictionaries", "title", "known", "words", "limit"} of the language's frequency lists, combined, or None when
    it has none."""
    return Ranker(language).frontier


class Ranker:
    """Ranks of many words in the language's frequency lists, combined, and their limit (frontier None without a
    list)."""

    def __init__(self, language: str):
        self.language = language
        refs = references(language)
        self.table = combined_ranks(language, refs) if refs else {}
        self.frontier = _frontier(language, refs, self.table) if refs else None

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
