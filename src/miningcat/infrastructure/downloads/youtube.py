from pathlib import Path

import yt_dlp

from miningcat.domain.languages import Language
from miningcat.infrastructure.downloads.handler import VideoHandler, resolve_downloaded_path


class YouTubeHandler(VideoHandler):
    """YouTube videos, with their captions in the language studied when there are some."""

    website = "YouTube"
    domains = ("youtube.com", "youtu.be", "m.youtube.com")
    url_hint = "https://www.youtube.com/watch?v=... or https://youtu.be/..."

    @staticmethod
    def subtitle_options(language: Language) -> dict:
        return {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(language.profile.youtube_caption_codes),
            "subtitlesformat": "srt",
            # yt-dlp's default rate limit for subtitles (1 request/s) often makes YouTube's timedtext endpoint answer
            # 429: 2 s is safer, and the pipeline falls back to Whisper or OCR when no captions come through.
            "sleep_interval_subtitles": 2,
        }

    def download(self, url: str, output_dir: Path, language: Language | None = None, **_ignored) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = self._options(output_dir)
        subtitle_opts = self.subtitle_options(language) if language is not None else {}
        try:
            with yt_dlp.YoutubeDL({**ydl_opts, **subtitle_opts}) as ydl:
                return resolve_downloaded_path(ydl, ydl.extract_info(url, download=True))
        except yt_dlp.utils.DownloadError:
            # Without captions (rate limit, or none in that language), the video is still downloaded.
            if not subtitle_opts:
                raise
            print("Warning: couldn't fetch platform subtitles (YouTube rate limit?); continuing without them.")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return resolve_downloaded_path(ydl, ydl.extract_info(url, download=True))
