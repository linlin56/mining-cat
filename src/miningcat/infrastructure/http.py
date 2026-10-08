import ssl
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


def get(url: str, params: dict | None = None, timeout: float = 8) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        return response.read()


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
