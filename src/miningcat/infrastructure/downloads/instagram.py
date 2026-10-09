from pathlib import Path

import yt_dlp

from miningcat.infrastructure.downloads.handler import VideoHandler, resolve_downloaded_path


class InstagramHandler(VideoHandler):
    """Instagram reels. `app_id`: the X-IG-App-ID yt-dlp sends (a numeric id, "ios" or "web")."""

    website = "Instagram"
    domains = ("instagram.com",)
    url_hint = "https://www.instagram.com/reel/..."

    def download(self, url: str, output_dir: Path, app_id: str = "web", **_ignored) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = self._options(output_dir, extractor_args={"instagram": {"app_id": [app_id]}})
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return resolve_downloaded_path(ydl, ydl.extract_info(url, download=True))
