from pathlib import Path

import yt_dlp

from language import Language
from video_handlers._common import BASE_YDL_OPTS, resolve_downloaded_path

DOMAINS = ("youtube.com", "youtu.be", "m.youtube.com")

# Candidate YouTube caption language codes to try, per Language (manual or auto-generated).
LANG_CODES: dict[Language, list[str]] = {
    Language.MANDARIN_TW: ["zh-Hant", "zh-TW", "zh"],
    Language.MANDARIN_CN: ["zh-Hans", "zh-CN", "zh"],
    Language.JAPANESE:    ["ja"],
    Language.FRENCH:      ["fr"],
    Language.ENGLISH_US:  ["en"],
    Language.ENGLISH_UK:  ["en-GB", "en"],
    Language.ITALIAN:     ["it"],
    Language.SPANISH:     ["es"],
    Language.POLISH:      ["pl"],
    Language.KOREAN:      ["ko"],
    Language.GERMAN:      ["de"],
    Language.PORTUGUESE:  ["pt-PT", "pt-BR", "pt"],
    Language.VIETNAMESE:  ["vi"],
    Language.CANTONESE_HK: ["yue", "zh-HK", "zh-Hant", "zh"],
}


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
            "subtitleslangs": LANG_CODES.get(language, [language.value.whisper_code]),
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
