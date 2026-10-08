import json
from abc import ABC, abstractmethod
from typing import Callable

from miningcat.infrastructure import http

# Recordings kept per word.
MAX_SOURCES = 6

# get(url, params) -> bytes
HttpGet = Callable[..., bytes]


class AudioSource(ABC):
    """A website with recordings of words. `get` fetches a URL (replaced by tests)."""

    def __init__(self, get: HttpGet = http.get):
        self._get = get

    def _json(self, url: str, params: dict) -> dict:
        return json.loads(self._get(url, {**params, "format": "json"}).decode("utf-8"))

    @abstractmethod
    def supports(self, language: str) -> bool:
        """Whether the website has recordings in this language."""

    @abstractmethod
    def find(self, language: str, expression: str, reading: str, words: list[str]) -> list[dict]:
        """[{"name", "url"}] recordings of a word (`words`: its spellings, e.g. both Chinese scripts)."""
