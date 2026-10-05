import hashlib
import json
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

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


def _get(url: str, params: dict | None = None) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=_ssl_context()) as response:
        return response.read()


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
    for word in words:
        data = _json(COMMONS_API, {"action": "query", "list": "search", "srnamespace": 6, "srlimit": 20,
                                   "srsearch": f'intitle:"{word}"'})
        for hit in data.get("query", {}).get("search", []):
            title = hit["title"]
            stem = title.split(":", 1)[-1].rsplit(".", 1)[0]
            # the whole word, not a sentence or a longer word containing it
            if _language_file(title, language) and stem.endswith(f"-{word}") and title not in titles:
                titles.append(title)
    return _file_urls(titles[:MAX_SOURCES])


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
    for attempt in attempts:
        try:
            for source in attempt():
                if source["url"] not in {s["url"] for s in found}:
                    found.append(source)
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            failed = True
    found = found[:MAX_SOURCES]
    if found or not failed:  # an offline failure is retried next time
        with _cache_lock:
            _cache[key] = found
    return found
