from abc import ABC, abstractmethod
from pathlib import Path

# Retries, for large files and slow connections.
BASE_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
}


def resolve_downloaded_path(ydl, info: dict) -> Path:
    """The file yt-dlp wrote (or found already there: yt-dlp only says so in its own logging, silenced by
    quiet=True, so it's printed here)."""
    if info.get("requested_downloads"):
        path = Path(info["requested_downloads"][0]["filepath"])
    else:
        path = Path(ydl.prepare_filename(info))
    if not info.get("__real_download"):
        print(f"Skipped download (already downloaded): {path}")
    return path


class VideoHandler(ABC):
    """Downloads the videos of a platform. To add one, see docs/how-to-contribute/add-video-platform.md."""

    # Name shown in the converter's list of websites.
    website: str
    # Domains of its URLs, without "www.".
    domains: tuple[str, ...]
    # Example URL shown as a placeholder.
    url_hint: str

    @staticmethod
    def _options(output_dir: Path, **extra) -> dict:
        return {
            **BASE_YDL_OPTS,
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "format": "bv*+ba/best",
            "merge_output_format": "mp4",
            **extra,
        }

    @abstractmethod
    def download(self, url: str, output_dir: Path, **options) -> Path:
        """Downloads the video (and what else the platform gives) to output_dir. Returns the video file.
        `options`: app_id (Instagram), language (subtitles to fetch)... a handler ignores the others."""
