from urllib.parse import urlparse

from miningcat.infrastructure.downloads.bilibili import BilibiliHandler
from miningcat.infrastructure.downloads.handler import VideoHandler
from miningcat.infrastructure.downloads.instagram import InstagramHandler
from miningcat.infrastructure.downloads.youtube import YouTubeHandler


class VideoHandlerRegistry:
    """The supported platforms, in the converter's order, and the handler of each domain."""

    def __init__(self, handlers: list[VideoHandler]):
        self.handlers = handlers
        self._by_domain = {domain: handler for handler in handlers for domain in handler.domains}

    def for_url(self, url: str) -> VideoHandler:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        handler = self._by_domain.get(host)
        if handler is None:
            raise ValueError(f"No video handler registered for host: {host!r}")
        return handler

    def for_website(self, website: str) -> VideoHandler | None:
        return next((h for h in self.handlers if h.website == website), None)

    @property
    def websites(self) -> list[str]:
        return [h.website for h in self.handlers]

    @property
    def url_hints(self) -> dict[str, str]:
        return {h.website: h.url_hint for h in self.handlers}


video_handlers = VideoHandlerRegistry([InstagramHandler(), YouTubeHandler(), BilibiliHandler()])


def get_handler(url: str) -> VideoHandler:
    return video_handlers.for_url(url)
