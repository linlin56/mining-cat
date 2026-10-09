from pathlib import Path

import yt_dlp

from miningcat.infrastructure.downloads.handler import VideoHandler


class BilibiliHandler(VideoHandler):
    """Bilibili videos."""

    website = "Bilibili"
    domains = ("bilibili.com",)
    url_hint = "https://www.bilibili.com/video/BV..."

    def download(self, url: str, output_dir: Path, **_ignored) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        with yt_dlp.YoutubeDL(self._options(output_dir)) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("requested_downloads"):
                return Path(info["requested_downloads"][0]["filepath"])
            return Path(ydl.prepare_filename(info))
