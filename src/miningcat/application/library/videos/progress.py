"""Where the user stopped in each video, and its preferences (language, subtitle tracks, their timings, audio track)."""
import re
import time

from miningcat.application.library.videos import store
from miningcat.domain.library.errors import VideoError
from miningcat.infrastructure.files.json_files import read_json, write_json

OFFSET_LIMIT_S = 600
SCALE_LIMITS = (0.9, 1.1)


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
    """The video's preferences. "timings": {track id: {"offset", "scale"}} of the tracks moved, video = scale ×
    track + offset."""
    prefs = read_json(store.video_folder(video_id) / "prefs.json", {})
    if "offset" in prefs:  # one offset for both tracks shown, before each track had its timing
        offset = prefs.pop("offset")
        tracks = store.read_meta(video_id).get("tracks", [])
        primary = prefs["primary"] if "primary" in prefs else next((t["id"] for t in tracks), "")
        timings = prefs.setdefault("timings", {})
        for track in {primary, prefs.get("secondary", "")} - {""}:
            if offset:
                timings.setdefault(track, {"offset": offset, "scale": 1.0})
    return prefs


def _timing(value) -> dict:
    try:
        offset = round(max(-OFFSET_LIMIT_S, min(OFFSET_LIMIT_S, float(value.get("offset", 0)))), 3)
        scale = float(value.get("scale", 1))
    except (AttributeError, TypeError, ValueError):
        raise VideoError("Invalid subtitle timing.")
    if not SCALE_LIMITS[0] <= scale <= SCALE_LIMITS[1]:
        raise VideoError("Invalid subtitle timing.")
    return {"offset": offset, "scale": scale}


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
    if "timings" in values:  # only the tracks given change; {"offset": 0, "scale": 1} is the track as is
        if not isinstance(values["timings"], dict):
            raise VideoError("Invalid subtitle timing.")
        timings = prefs.setdefault("timings", {})
        for track, value in values["timings"].items():
            if track not in track_ids:
                raise VideoError("No such subtitle track.")
            value = _timing(value)
            if value == {"offset": 0.0, "scale": 1.0}:
                timings.pop(track, None)
            else:
                timings[track] = value
    if "audio_track" in values:
        track = values["audio_track"]
        if not isinstance(track, int) or not 0 <= track < max(1, len(meta.get("audio", []))):
            raise VideoError("No such audio track.")
        prefs["audio_track"] = track
    write_json(store.video_folder(video_id) / "prefs.json", prefs)
    return prefs
