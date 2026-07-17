from urllib.parse import urlparse

from . import instagram

_HANDLERS = {
    domain: instagram for domain in instagram.DOMAINS
}


def get_handler(url: str):
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    handler = _HANDLERS.get(host)
    if handler is None:
        raise ValueError(f"No video handler registered for host: {host!r}")
    return handler
