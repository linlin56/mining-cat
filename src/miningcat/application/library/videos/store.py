"""Where the player's library keeps its videos: one folder per video (library/videos/<id>), with its meta.json."""
import re
import subprocess
import threading
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.library.errors import VideoError
from miningcat.infrastructure.files.json_files import read_json, write_json

# meta.json reads and writes
lock = threading.RLock()
# The ffmpeg process preparing each video, killed when the video is deleted.
processes: dict[str, subprocess.Popen] = {}


def videos_dir() -> Path:
    return paths.library_videos


def video_folder(video_id: str) -> Path:
    """The folder of a video (its id is checked: it comes from the browser)."""
    if not re.fullmatch(r"[0-9a-f]{16}", video_id or ""):
        raise VideoError("Unknown video.")
    return videos_dir() / video_id


def source_file(folder: Path) -> Path:
    source = next(folder.glob("source.*"), None)
    if source is None:
        raise VideoError("The video's file is missing from the library.")
    return source


def read_meta(video_id: str) -> dict:
    meta = read_json(video_folder(video_id) / "meta.json", None)
    if meta is None:
        raise VideoError("Unknown video.")
    return meta


def update_meta(video_id: str, **changes) -> dict:
    with lock:
        meta = read_meta(video_id)
        meta.update(changes)
        write_json(video_folder(video_id) / "meta.json", meta)
        return meta


def read_file(video_id: str, name: str, default) -> dict:
    return read_json(video_folder(video_id) / name, default)


def write_file(video_id: str, name: str, data) -> None:
    write_json(video_folder(video_id) / name, data)


def spawn(target, *args) -> None:
    """Background work (replaced by a direct call in the tests)."""
    threading.Thread(target=target, args=args, daemon=True, name="miningcat-video").start()
