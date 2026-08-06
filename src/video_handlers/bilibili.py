from pathlib import Path

import yt_dlp

from video_handlers._common import BASE_YDL_OPTS

DOMAINS = ("bilibili.com",)


def download(url: str, output_dir: Path, **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        **BASE_YDL_OPTS,
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("requested_downloads"):
            return Path(info["requested_downloads"][0]["filepath"])
        return Path(ydl.prepare_filename(info))
