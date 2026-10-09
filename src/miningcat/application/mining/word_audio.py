import re
import threading
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.text.chinese_script import chinese_counterpart
from miningcat.domain.text.readings import reading_match
from miningcat.domain.text.zhuyin import pinyin_to_zhuyin
from miningcat.infrastructure import http
from miningcat.infrastructure.word_audio.japanesepod101 import JapanesePod101Source
from miningcat.infrastructure.word_audio.source import MAX_SOURCES, AudioSource, HttpGet
from miningcat.infrastructure.word_audio.wikimedia import LinguaLibreSource, WiktionarySource


# Wiktionary names Mandarin recordings after their pinyin (Zh-zhōng.ogg): those of the reading come first, those of
# another reading (中 zhòng for zhōng) are left out. Recordings named after the characters keep their place.
def _for_reading(found: list[dict], reading: str) -> list[dict]:
    ranked = []
    for source in found:
        name = urllib.parse.unquote(source["url"].rsplit("/", 1)[-1])
        stem = re.sub(r"^zh-", "", name.split(".", 1)[0], flags=re.I)
        if not re.fullmatch(r"[A-Za-zÀ-ɏ'\s]+", stem) or not pinyin_to_zhuyin(stem):
            ranked.append((1, source))  # not a pinyin name
        elif reading_match(stem, reading, "zh") == 2:
            ranked.append((0, source))
    return [source for _, source in sorted(ranked, key=lambda r: r[0])]


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
        if language == "zh" and reading:
            found = _for_reading(found, reading)
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
