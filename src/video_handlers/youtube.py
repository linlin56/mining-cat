from pathlib import Path

import yt_dlp

from miningcat.domain.languages import Language
from video_handlers._common import BASE_YDL_OPTS, resolve_downloaded_path

DOMAINS = ("youtube.com", "youtu.be", "m.youtube.com")

def download(url: str, output_dir: Path, language: Language | None = None, **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        **BASE_YDL_OPTS,
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
    }
    subtitle_opts = {}
    if language is not None:
        subtitle_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(language.profile.youtube_caption_codes),
            "subtitlesformat": "srt",
            # yt-dlp's default subtitle download rate limit is 1 request/sec, which is too slow for YouTube's timedtext endpoint and often triggers a 429 rate limit. 
            # Set to 2 seconds to be safe, since the pipeline already falls back to Whisper/OCR when no platform subs come through.
            "sleep_interval_subtitles": 2,
        }
    try:
        with yt_dlp.YoutubeDL({**ydl_opts, **subtitle_opts}) as ydl:
            info = ydl.extract_info(url, download=True)
            return resolve_downloaded_path(ydl, info)
    except yt_dlp.utils.DownloadError:
        # If for some reason we can't get subtitles, we should still download the video. 
        # This can happen with rate limits, or if the requested language isn't available on the platform.
        if not subtitle_opts:
            raise
        print("Warning: couldn't fetch platform subtitles (YouTube rate limit?); "
              "continuing without them.")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return resolve_downloaded_path(ydl, info)
