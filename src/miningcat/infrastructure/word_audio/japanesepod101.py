import hashlib
import urllib.parse

from miningcat.infrastructure.word_audio.source import AudioSource


class JapanesePod101Source(AudioSource):
    """JapanesePod101's recordings of Japanese words, by writing and reading."""

    URL = "https://assets.languagepod101.com/dictionary/japanese/audiomp3.php"
    # SHA-256 of its "The audio for this clip is currently not available" clip (same check as Yomitan).
    MISSING_SHA256 = "ae6398b5a27bc8c0a771df6c907ade794be15518174773c58c7c7ddd17098906"

    def supports(self, language: str) -> bool:
        return language == "ja"

    def find(self, language: str, expression: str, reading: str, words: list[str]) -> list[dict]:
        params = {"kanji": expression, "kana": reading or expression}
        url = f"{self.URL}?{urllib.parse.urlencode(params)}"
        data = self._get(url)
        if not data or hashlib.sha256(data).hexdigest() == self.MISSING_SHA256:
            return []
        return [{"name": "JapanesePod101", "url": url}]
