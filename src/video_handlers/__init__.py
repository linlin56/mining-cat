from urllib.parse import urlparse

from . import instagram, youtube

_HANDLER_MODULES = (instagram, youtube)
_HANDLERS = {
    domain: module for module in _HANDLER_MODULES for domain in module.DOMAINS
}


def get_handler(url: str):
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    handler = _HANDLERS.get(host)
    if handler is None:
        raise ValueError(f"No video handler registered for host: {host!r}")
    return handler
