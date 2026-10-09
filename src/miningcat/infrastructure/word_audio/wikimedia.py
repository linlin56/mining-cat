"""Recordings of Wiktionary and of Lingua Libre, both hosted on Wikimedia Commons."""
import re
from concurrent.futures import ThreadPoolExecutor

from miningcat.infrastructure.word_audio.source import MAX_SOURCES, AudioSource

WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# File name prefixes of each language's recordings: Wiktionary's own ("Fr-manger.ogg") and Lingua Libre's.
FILE_PREFIXES = {
    "ja": ("ja-", "ll-q5287 (jpn)"),
    "zh": ("zh-", "cmn-", "ll-q9192 (cmn)"),
    "yue": ("yue-", "zh-yue-", "ll-q9186 (yue)"),
    "nan": ("nan-", "zh-nan-", "ll-q36495 (nan)"),
    "ko": ("ko-", "ll-q9176 (kor)"),
    "en": ("en-", "ll-q1860 (eng)"),
    "fr": ("fr-", "ll-q150 (fra)"),
    "de": ("de-", "ll-q188 (deu)"),
    "es": ("es-", "ll-q1321 (spa)"),
    "it": ("it-", "ll-q652 (ita)"),
    "pt": ("pt-", "ll-q5146 (por)"),
    "pl": ("pl-", "ll-q809 (pol)"),
    "ru": ("ru-", "ll-q7737 (rus)"),
    "vi": ("vi-", "ll-q9199 (vie)"),
}
AUDIO_SUFFIXES = (".ogg", ".oga", ".opus", ".mp3", ".wav", ".flac", ".webm")


# "LL-Q150 (fra)-Pamputt-manger.wav" -> "Lingua Libre (Pamputt)", "Fr-manger-fr-FR-Paris.ogg" -> "Wiktionary"
def label(name: str) -> str:
    m = re.match(r"LL-Q\d+ \([^)]*\)-(.+?)-", name)
    return f"Lingua Libre ({m.group(1)})" if m else "Wiktionary"


def is_language_file(title: str, language: str) -> bool:
    name = title.split(":", 1)[-1].lower()
    if language == "zh" and re.match(r"zh-[a-z]{2,3}-", name):
        return False  # another Chinese language: Zh-wuu-謝謝 (Shanghainese), Zh-yue-你好 (Cantonese)
    return name.endswith(AUDIO_SUFFIXES) and name.startswith(FILE_PREFIXES.get(language, ()))


# The MP3 that Commons transcodes every recording to.
def mp3_url(original: str) -> str:
    original = original.split("?", 1)[0]
    if original.lower().endswith(".mp3"):
        return original
    name = original.rsplit("/", 1)[1]
    return original.replace("/commons/", "/commons/transcoded/", 1) + f"/{name}.mp3"


class WikimediaSource(AudioSource):
    """Recordings named after their language and word on Wikimedia Commons."""

    def supports(self, language: str) -> bool:
        return language in FILE_PREFIXES

    def _file_urls(self, titles: list[str]) -> list[dict]:
        if not titles:
            return []
        data = self._json(WIKTIONARY_API, {"action": "query", "titles": "|".join(titles[:50]), "prop": "imageinfo", "iiprop": "url"})
        by_title = {p.get("title"): p for p in data.get("query", {}).get("pages", {}).values()}
        out = []
        for title in titles:
            info = (by_title.get(title) or {}).get("imageinfo")
            if info:
                out.append({"name": label(title.split(":", 1)[-1]), "url": mp3_url(info[0]["url"])})
        return out


class WiktionarySource(WikimediaSource):
    """The recordings shown on the Wiktionary page of a word."""

    def find(self, language: str, expression: str, reading: str, words: list[str]) -> list[dict]:
        data = self._json(WIKTIONARY_API, {"action": "query", "titles": "|".join(words), "prop": "images", "imlimit": 200})
        titles = [i["title"] for p in data.get("query", {}).get("pages", {}).values() for i in p.get("images", [])
                  if is_language_file(i["title"], language)]
        return self._file_urls(titles[:MAX_SOURCES])


class LinguaLibreSource(WikimediaSource):
    """Lingua Libre's recordings, found by a search on Commons."""

    def find(self, language: str, expression: str, reading: str, words: list[str]) -> list[dict]:
        titles = []

        def search(word: str) -> dict:
            return self._json(COMMONS_API, {"action": "query", "list": "search", "srnamespace": 6, "srlimit": 20,
                                            "srsearch": f'intitle:"{word}"'})

        with ThreadPoolExecutor(max_workers=len(words) or 1) as pool:
            results = list(pool.map(search, words))
        for word, data in zip(words, results):
            for hit in data.get("query", {}).get("search", []):
                title = hit["title"]
                stem = title.split(":", 1)[-1].rsplit(".", 1)[0]
                # the whole word, not a sentence or a longer word containing it
                if is_language_file(title, language) and stem.endswith(f"-{word}") and title not in titles:
                    titles.append(title)
        return self._file_urls(titles[:MAX_SOURCES])
