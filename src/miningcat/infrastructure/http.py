import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from miningcat.config.app_info import GITHUB_URL

USER_AGENT = f"MiningCat ({GITHUB_URL})"


def ssl_context() -> ssl.SSLContext:
    """python.org's macOS builds have no root certificates until "Install Certificates" is run: certifi's are
    used when it's there."""
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


def get(url: str, params: dict | None = None, timeout: float = 8) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    wikimedia = bool(_WIKIMEDIA.match(url))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        if wikimedia:
            _wait_turn()
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == RETRIES:
                raise
            time.sleep(_retry_delay(exc, attempt))
    raise AssertionError("unreachable")


def download(url: str, timeout: float = 300, progress: Callable[[int, int], None] | None = None) -> bytes:
    """The content of a URL, read in chunks: `progress(bytes read, total bytes or 0)` is called after each."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        total = int(response.headers.get("Content-Length") or 0)
        data = bytearray()
        while chunk := response.read(256 * 1024):
            data.extend(chunk)
            if progress:
                progress(len(data), total)
        return bytes(data)
