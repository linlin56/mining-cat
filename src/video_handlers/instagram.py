# video_handlers/instagram.py - Instagram video download handler (yt-dlp based).
#
# Instagram's private API requires an X-IG-App-ID header. yt-dlp exposes this
# as the "app_id" extractor arg: the numeric app ID, "ios", or "web" (default).
# See: https://github.com/yt-dlp/yt-dlp#instagram

from pathlib import Path

import yt_dlp

DOMAINS = ("instagram.com",)


def download(url: str, output_dir: Path, app_id: str = "web") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "extractor_args": {"instagram": {"app_id": [app_id]}},
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("requested_downloads"):
            return Path(info["requested_downloads"][0]["filepath"])
        return Path(ydl.prepare_filename(info))
