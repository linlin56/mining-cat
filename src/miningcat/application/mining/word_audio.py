import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.text.chinese_script import chinese_counterpart
from miningcat.infrastructure import http
from miningcat.infrastructure.word_audio.japanesepod101 import JapanesePod101Source
from miningcat.infrastructure.word_audio.source import MAX_SOURCES, AudioSource, HttpGet
from miningcat.infrastructure.word_audio.wikimedia import LinguaLibreSource, WiktionarySource


class WordAudioFinder:
    """Recordings of a word from every website that has its language, fetched when the user asks for them."""

    def __init__(self, get: HttpGet = http.get):
        self.sources: list[AudioSource] = [JapanesePod101Source(get), WiktionarySource(get), LinguaLibreSource(get)]
        self._cache: dict[tuple, list[dict]] = {}
        self._lock = threading.Lock()

    def find(self, language: str, expression: str, reading: str = "") -> list[dict]:
        """[{"name", "url"}], best first. Sources that fail (offline...) are skipped."""
        key = (language, expression, reading)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        words = [expression]
        if language in CHINESE_LANGUAGES:
            other = chinese_counterpart(expression, language)
            if other:
                words.append(other[1])
        sources = [source for source in self.sources if source.supports(language)]
        found: list[dict] = []
        failed = False
        # all the sources at once: the slowest one sets the time, not their sum
        with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
            futures = [pool.submit(source.find, language, expression, reading, words) for source in sources]
        for future in futures:
            try:
                for recording in future.result():
                    if recording["url"] not in {r["url"] for r in found}:
                        found.append(recording)
            except (urllib.error.URLError, OSError, ValueError, KeyError):
                failed = True
        found = found[:MAX_SOURCES]
        if found or not failed:  # an offline failure is retried next time
            with self._lock:
                self._cache[key] = found
        return found

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def is_cached(self, language: str, expression: str, reading: str = "") -> bool:
        with self._lock:
            return (language, expression, reading) in self._cache


finder = WordAudioFinder()


def sources(language: str, expression: str, reading: str = "") -> list[dict]:
    """Online recordings of a word: [{"name", "url"}], best first."""
    return finder.find(language, expression, reading)
