from pathlib import Path

from miningcat.config.paths import paths
from miningcat.infrastructure.downloads.registry import get_handler


def download_video(url: str, output_dir: Path | None = None, **options) -> Path:
    """Downloads an online video (to output/videos by default) with the handler of its platform."""
    handler = get_handler(url)
    print(f"Downloading video: {url}")
    path = handler.download(url, output_dir or paths.videos, **options)
    print(f"Downloaded: {path}")
    return path
