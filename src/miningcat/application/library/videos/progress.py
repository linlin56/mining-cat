"""Where the user stopped in each video, and its preferences (language, subtitle tracks, offset, audio track)."""
import re
import time

from miningcat.application.library.videos import store
from miningcat.domain.library.errors import VideoError
from miningcat.infrastructure.files.json_files import read_json, write_json

OFFSET_LIMIT_S = 600


def get_progress(video_id: str) -> dict:
    return read_json(store.video_folder(video_id) / "progress.json", {})


def save_progress(video_id: str, position) -> dict:
    meta = store.read_meta(video_id)
    try:
        position = max(0.0, float(position))
    except (TypeError, ValueError):
        raise VideoError("Invalid position.")
    duration = meta.get("duration") or 0
    percent = min(100.0, position / duration * 100) if duration else 0
    progress = {"time": round(position, 2), "percent": round(percent, 2), "updated": time.time()}
    write_json(store.video_folder(video_id) / "progress.json", progress)
    return progress


def get_prefs(video_id: str) -> dict:
    return read_json(store.video_folder(video_id) / "prefs.json", {})


def save_prefs(video_id: str, values: dict) -> dict:
    meta = store.read_meta(video_id)
    prefs = get_prefs(video_id)
    track_ids = {t["id"] for t in meta.get("tracks", [])}
    if "language" in values:
        language = str(values["language"] or "").strip()
        if language and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", language):
            raise VideoError("Invalid language tag.")
        prefs["language"] = language
    for key in ("primary", "secondary"):
        if key in values:
            track = str(values[key] or "")
            if track and track not in track_ids:
                raise VideoError("No such subtitle track.")
            prefs[key] = track
    if "offset" in values:
        try:
            prefs["offset"] = round(max(-OFFSET_LIMIT_S, min(OFFSET_LIMIT_S, float(values["offset"]))), 3)
        except (TypeError, ValueError):
            raise VideoError("Invalid subtitle offset.")
    if "audio_track" in values:
        track = values["audio_track"]
        if not isinstance(track, int) or not 0 <= track < max(1, len(meta.get("audio", []))):
            raise VideoError("No such audio track.")
        prefs["audio_track"] = track
    write_json(store.video_folder(video_id) / "prefs.json", prefs)
    return prefs
