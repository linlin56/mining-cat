"""The player's library: its videos, and the files the browser gets."""
import shutil
from pathlib import Path

from miningcat.application.library.videos import store
from miningcat.application.library.videos.preparation import get_meta
from miningcat.application.library.videos.progress import get_prefs, get_progress
from miningcat.domain.library.errors import VideoError


def list_videos() -> list[dict]:
    if not store.videos_dir().exists():
        return []
    videos = []
    for folder in store.videos_dir().iterdir():
        if not (folder / "meta.json").exists():
            continue
        try:
            meta = get_meta(folder.name)
        except (VideoError, OSError, ValueError):
            continue
        progress = get_progress(folder.name)
        videos.append({
            "id": meta["id"], "title": meta["title"], "duration": meta.get("duration"),
            "status": meta.get("status"), "progress": meta.get("progress", 0), "error": meta.get("error"),
            "thumb": (folder / "thumb.jpg").exists(), "tracks": len(meta.get("tracks", [])),
            "added": meta.get("added", 0), "opened": progress.get("updated", 0), "percent": progress.get("percent", 0),
            "language": get_prefs(folder.name).get("language") or meta.get("language") or "",
        })
    videos.sort(key=lambda v: (v["opened"] or 0, v["added"] or 0), reverse=True)
    return videos


def file_path(video_id: str) -> Path:
    """The file the browser plays: the copy for the browser when there is one, else the original."""
    folder = store.video_folder(video_id)
    meta = get_meta(video_id)
    if meta.get("status") != "ready":
        raise VideoError("The video isn't ready yet.")
    play = folder / "play.mp4"
    return play if play.exists() else store.source_file(folder)


def thumb_path(video_id: str) -> Path:
    path = store.video_folder(video_id) / "thumb.jpg"
    if not path.is_file():
        raise VideoError("No thumbnail.")
    return path


def delete_video(video_id: str) -> None:
    folder = store.video_folder(video_id)
    with store.lock:
        proc = store.processes.get(video_id)
        if proc is not None:
            proc.kill()
        if folder.exists():
            shutil.rmtree(folder)
