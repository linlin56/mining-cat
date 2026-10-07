import hashlib
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = "MiningCat (https://github.com/linlin56/mining-cat)"
TIMEOUT_S = 8

JPOD_URL = "https://assets.languagepod101.com/dictionary/japanese/audiomp3.php"
# SHA-256 of JapanesePod101's "The audio for this clip is currently not available" clip (same check as Yomitan).
JPOD_MISSING_SHA256 = "ae6398b5a27bc8c0a771df6c907ade794be15518174773c58c7c7ddd17098906"
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
MAX_SOURCES = 6

_cache: dict[tuple, list[dict]] = {}
_cache_lock = threading.Lock()


# python.org's macOS builds have no root certificates until "Install Certificates" is run: use certifi's when it's there.
def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# Wikimedia answers 429 (too many requests) to a burst, e.g. a CSV import downloading a recording per card: its
# requests go one at a time, a little apart, and are tried again (after the Retry-After it asks for) when refused.
_WIKIMEDIA = re.compile(r"^https?://([^/]+\.)?(wikimedia|wiktionary|wikipedia)\.org/", re.I)
WIKIMEDIA_GAP_S = 0.3
RETRIES = 4
RETRY_MAX_WAIT_S = 30
_wikimedia_lock = threading.Lock()
_wikimedia_last = 0.0


def _wait_turn() -> None:
    global _wikimedia_last
    with _wikimedia_lock:
        wait = _wikimedia_last + WIKIMEDIA_GAP_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _wikimedia_last = time.monotonic()


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    try:
        asked = float(exc.headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        asked = 0
    return min(RETRY_MAX_WAIT_S, max(asked, 2 ** attempt))


def _get(url: str, params: dict | None = None, timeout: float = TIMEOUT_S) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    wikimedia = bool(_WIKIMEDIA.match(url))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        if wikimedia:
            _wait_turn()
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == RETRIES:
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise AssertionError("unreachable")


def download(url: str) -> bytes:
    """A recording found by sources(), downloaded by MiningCat (with the retries above) rather than by Anki."""
    return _get(url, timeout=30)


def _json(url: str, params: dict) -> dict:
    return json.loads(_get(url, {**params, "format": "json"}).decode("utf-8"))


def japanesepod101(expression: str, reading: str) -> list[dict]:
    params = {"kanji": expression, "kana": reading or expression}
    url = f"{JPOD_URL}?{urllib.parse.urlencode(params)}"
    data = _get(url)
    if not data or hashlib.sha256(data).hexdigest() == JPOD_MISSING_SHA256:
        return []
    return [{"name": "JapanesePod101", "url": url}]


# "LL-Q150 (fra)-Pamputt-manger.wav" -> "Lingua Libre (Pamputt)", "Fr-manger-fr-FR-Paris.ogg" -> "Wiktionary"
def _label(name: str) -> str:
    m = re.match(r"LL-Q\d+ \([^)]*\)-(.+?)-", name)
    return f"Lingua Libre ({m.group(1)})" if m else "Wiktionary"


def _language_file(title: str, language: str) -> bool:
    name = title.split(":", 1)[-1].lower()
    if language == "zh" and re.match(r"zh-[a-z]{2,3}-", name):
        return False  # another Chinese language: Zh-wuu-謝謝 (Shanghainese), Zh-yue-你好 (Cantonese)
    return name.endswith(AUDIO_SUFFIXES) and name.startswith(FILE_PREFIXES.get(language, ()))


# The MP3 that Commons transcodes every recording to.
def _mp3_url(original: str) -> str:
    original = original.split("?", 1)[0]
    if original.lower().endswith(".mp3"):
        return original
    name = original.rsplit("/", 1)[1]
    return original.replace("/commons/", "/commons/transcoded/", 1) + f"/{name}.mp3"


def _file_urls(titles: list[str]) -> list[dict]:
    if not titles:
        return []
    data = _json(WIKTIONARY_API, {"action": "query", "titles": "|".join(titles[:50]), "prop": "imageinfo", "iiprop": "url"})
    by_title = {p.get("title"): p for p in data.get("query", {}).get("pages", {}).values()}
    out = []
    for title in titles:
        info = (by_title.get(title) or {}).get("imageinfo")
        if info:
            out.append({"name": _label(title.split(":", 1)[-1]), "url": _mp3_url(info[0]["url"])})
    return out


def wiktionary(language: str, words: list[str]) -> list[dict]:
    data = _json(WIKTIONARY_API, {"action": "query", "titles": "|".join(words), "prop": "images", "imlimit": 200})
    titles = [i["title"] for p in data.get("query", {}).get("pages", {}).values() for i in p.get("images", [])
              if _language_file(i["title"], language)]
    return _file_urls(titles[:MAX_SOURCES])


def lingua_libre(language: str, words: list[str]) -> list[dict]:
    titles = []
    search = lambda word: _json(COMMONS_API, {"action": "query", "list": "search", "srnamespace": 6, "srlimit": 20,
                                              "srsearch": f'intitle:"{word}"'})
    with ThreadPoolExecutor(max_workers=len(words) or 1) as pool:
        results = list(pool.map(search, words))
    for word, data in zip(words, results):
        for hit in data.get("query", {}).get("search", []):
            title = hit["title"]
            stem = title.split(":", 1)[-1].rsplit(".", 1)[0]
            # the whole word, not a sentence or a longer word containing it
            if _language_file(title, language) and stem.endswith(f"-{word}") and title not in titles:
                titles.append(title)
    return _file_urls(titles[:MAX_SOURCES])


# Wiktionary names Mandarin recordings after their pinyin (Zh-zhōng.ogg): those of the reading come first, those of
# another reading (中 zhòng for zhōng) are left out. Recordings named after the characters keep their place.
def _for_reading(found: list[dict], reading: str) -> list[dict]:
    from mining.languages import reading_match
    from mining.zhuyin import pinyin_to_zhuyin

    ranked = []
    for source in found:
        name = urllib.parse.unquote(source["url"].rsplit("/", 1)[-1])
        stem = re.sub(r"^zh-", "", name.split(".", 1)[0], flags=re.I)
        if not re.fullmatch(r"[A-Za-zÀ-ɏ'\s]+", stem) or not pinyin_to_zhuyin(stem):
            ranked.append((1, source))  # not a pinyin name
        elif reading_match(stem, reading, "zh") == 2:
            ranked.append((0, source))
    return [source for _, source in sorted(ranked, key=lambda r: r[0])]


def sources(language: str, expression: str, reading: str = "") -> list[dict]:
    """Recordings of a word: [{"name", "url"}], best first. Sources that fail (offline...) are skipped."""
    key = (language, expression, reading)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    words = [expression]
    if language in ("zh", "yue", "nan"):
        from mining.languages import chinese_counterpart
        other = chinese_counterpart(expression, language)
        if other:
            words.append(other[1])
    found: list[dict] = []
    attempts = []
    if language == "ja":
        attempts.append(lambda: japanesepod101(expression, reading))
    if language in FILE_PREFIXES:
        attempts += [lambda: wiktionary(language, words), lambda: lingua_libre(language, words)]
    failed = False
    # all the sources at once: the slowest one sets the time, not their sum
    with ThreadPoolExecutor(max_workers=max(1, len(attempts))) as pool:
        futures = [pool.submit(attempt) for attempt in attempts]
    for future in futures:
        try:
            for source in future.result():
                if source["url"] not in {s["url"] for s in found}:
                    found.append(source)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            failed = True
    if language == "zh" and reading:
        found = _for_reading(found, reading)
    found = found[:MAX_SOURCES]
    if found or not failed:  # an offline failure is retried next time
        with _cache_lock:
            _cache[key] = found
    return found
