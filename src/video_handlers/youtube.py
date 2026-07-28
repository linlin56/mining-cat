from pathlib import Path

import yt_dlp

from language import Language
from video_handlers._common import resolve_downloaded_path

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
}


def download(url: str, output_dir: Path, language: Language | None = None, **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if language is not None:
        ydl_opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": LANG_CODES.get(language, [language.value.whisper_code]),
            "subtitlesformat": "srt",
        })
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return resolve_downloaded_path(ydl, info)
