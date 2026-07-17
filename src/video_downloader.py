from pathlib import Path

from config import DIR_VIDEOS
from video_handlers import get_handler

# Download videos from supported online platforms (via yt-dlp handlers).
def download_video(url: str, output_dir: Path | None = None, **options) -> Path:
    handler = get_handler(url)
    print(f"Downloading video: {url}")
    path = handler.download(url, output_dir or DIR_VIDEOS, **options)
    print(f"Downloaded: {path}")
    return path
