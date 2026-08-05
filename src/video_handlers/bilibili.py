from pathlib import Path

import yt_dlp

DOMAINS = ("bilibili.com",)


def download(url: str, output_dir: Path, **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("requested_downloads"):
            return Path(info["requested_downloads"][0]["filepath"])
        return Path(ydl.prepare_filename(info))
