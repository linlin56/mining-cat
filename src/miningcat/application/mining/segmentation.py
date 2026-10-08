import hashlib
import threading
from collections import OrderedDict

from miningcat.application.mining import preferences, words
from miningcat.application.mining.frequency import Ranker
from miningcat.domain.dictionary.deinflection import transformer_for
from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.segmentation.lexicon import Lexicon, build_lexicon
from miningcat.domain.segmentation.splitter import split_words
from miningcat.domain.text.sentences import sentence_spans
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries

# Segmentations kept in memory (a chapter is segmented again when a dictionary changes).
CACHE_SIZE = 64

Tokens = list[tuple[int, int, str | None]]


class LexiconCache:
    """The lexicon of each language, loaded once and reloaded when its dictionaries change."""

    def __init__(self):
        self._lexicons: dict[str, Lexicon] = {}
        self._lock = threading.Lock()

    def get(self, language: str) -> Lexicon:
        with database.session() as conn:
            signature = (str(database.path),) + DictionaryQueries(conn).signature(language)
        with self._lock:
            cached = self._lexicons.get(language)
            if cached is not None and cached.signature == signature:
                return cached
            with database.session() as conn:
                lex = build_lexicon(language, signature, DictionaryQueries(conn).headwords(language),
                                    transformer_for(language))
            self._lexicons[language] = lex
            return lex

    def clear(self) -> None:
        with self._lock:
            self._lexicons.clear()


class SegmentationCache:
    """The last segmented texts (least recently used ones are forgotten first)."""

    def __init__(self, size: int = CACHE_SIZE):
        self._size = size
        self._tokens: OrderedDict[tuple, Tokens] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> Tokens | None:
        with self._lock:
            if key in self._tokens:
                self._tokens.move_to_end(key)
                return self._tokens[key]
        return None

    def put(self, key: tuple, tokens: Tokens) -> None:
        with self._lock:
            self._tokens[key] = tokens
            while len(self._tokens) > self._size:
                self._tokens.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()


_lexicons = LexiconCache()
_segmentations = SegmentationCache()


def lexicon(language: str) -> Lexicon:
    """Headwords of the enabled dictionaries of `language`."""
    return _lexicons.get(language)


def segment(language: str, text: str) -> Tokens:
    """Words of `text` as (start, length, headword), headword None for a word missing from the dictionaries."""
    lex = lexicon(language)
    key = (language, lex.signature, hashlib.sha1(text.encode("utf-8")).hexdigest())
    tokens = _segmentations.get(key)
    if tokens is None:
        tokens = split_words(lex, text, transformer_for(language))
        _segmentations.put(key, tokens)
    return tokens


def statuses(language: str, headwords: list[str]) -> dict[str, dict]:
    """{headword: {"form", "status"}}: the form a word is saved under (the script the user learns), and its status."""
    preference = preferences.chinese_script_preference(language) if language in CHINESE_LANGUAGES else None
    forms = {h: words.preferred_form(language, h, preference) for h in dict.fromkeys(headwords)}
    found = words.statuses_for(language, list(set(forms.values())))
    return {h: {"form": form, "status": found.get(form, "new")} for h, form in forms.items()}


def colour(language: str, text: str) -> dict:
    """Words of `text` with their status: {"words": [{headword, form, status}], "tokens": [[start, length, word index]],
    "sentences": [[start, end]]}. Words missing from the dictionaries have the index -1. The sentences are for the
    comprehension and the recommended sentences (see comprehension.py)."""
    tokens = segment(language, text)
    headwords = list(dict.fromkeys(t[2] for t in tokens if t[2] is not None))
    index = {h: i for i, h in enumerate(headwords)}
    info = statuses(language, headwords)
    ranker = Ranker(language)
    return {
        "language": language,
        # rank: in the language's frequency list (None without one, or for a word it doesn't have)
        "words": [{"headword": h, **info[h], "rank": ranker.rank(h, info[h]["form"])} for h in headwords],
        # the recommended sentences only teach words ranked up to frequency["limit"] (see frequency.py)
        "frequency": ranker.frontier,
        "tokens": [[start, length, index[h] if h is not None else -1] for start, length, h in tokens],
        "sentences": [list(span) for span in sentence_spans(text)] if tokens else [],
    }


def clear_cache() -> None:
    _segmentations.clear()
    _lexicons.clear()
