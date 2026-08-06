from pathlib import Path

import yt_dlp

from video_handlers._common import BASE_YDL_OPTS, resolve_downloaded_path

DOMAINS = ("instagram.com",)


def download(url: str, output_dir: Path, app_id: str = "web", **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        **BASE_YDL_OPTS,
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "extractor_args": {"instagram": {"app_id": [app_id]}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return resolve_downloaded_path(ydl, info)
