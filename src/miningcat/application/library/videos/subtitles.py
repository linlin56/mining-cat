"""The subtitle tracks of a video: stored as SRT (library/videos/<id>/subs), from files, platforms or the video."""
import hashlib
import re
import tempfile
from pathlib import Path

from miningcat.application.library.videos.store import (
    lock,
    read_file,
    read_meta,
    update_meta,
    video_folder,
    write_file,
)
from miningcat.domain.library.errors import VideoError
from miningcat.domain.subtitles.srt import parse_srt
from miningcat.domain.text.decoding import decode_text
from miningcat.domain.text.fullwidth_punctuation import fullwidth_punctuation
from miningcat.infrastructure.media.subtitle_files import (
    convert_to_srt,
    extract_subtitle_streams,
    text_subtitle_streams,
)

SUBTITLE_EXTENSIONS = ("srt", "vtt", "ass", "ssa")

_ASS_TAGS = re.compile(r"\{\\[^}]*\}")
_SPACES = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _SPACES.sub(" ", _ASS_TAGS.sub("", text)).strip()


def parse_subtitles(text: str) -> list[dict]:
    """{"start", "end", "text"} of each line of an SRT file, without formatting, in order."""
    cues = [{"start": round(c.start, 3), "end": round(c.end, 3), "text": _clean(c.text)} for c in parse_srt(text)]
    return sorted((c for c in cues if c["text"] and c["end"] > c["start"]), key=lambda c: c["start"])


def add_subtitles(video_id: str, filename: str, data: bytes, origin: str = "file", label: str | None = None) -> dict:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUBTITLE_EXTENSIONS:
        raise VideoError(f"Unsupported subtitles: .{ext or '?'} (supported: {', '.join(SUBTITLE_EXTENSIONS)})")
    text = decode_text(data) if ext == "srt" else convert_to_srt(decode_text(data), ext)
    found = parse_subtitles(text)
    if not found:
        raise VideoError(f"No subtitles found in {filename}.")
    digest = hashlib.sha256("\n".join(f"{c['start']} {c['text']}" for c in found).encode()).hexdigest()[:16]
    folder = video_folder(video_id)
    with lock:
        tracks = read_meta(video_id).get("tracks", [])
        same = next((t for t in tracks if t.get("sha") == digest), None)
        if same:
            return same
        number = 1 + max((int(t["id"]) for t in tracks), default=0)
        (folder / "subs").mkdir(exist_ok=True)
        (folder / "subs" / f"{number:03d}.srt").write_text(text, encoding="utf-8")
        track = {"id": str(number), "label": label or Path(filename).stem, "origin": origin,
                 "cues": len(found), "sha": digest}
        update_meta(video_id, tracks=[*tracks, track])
    return track


def cues(video_id: str, track_id: str, punctuation: str = "") -> list[dict]:
    """The lines of a track; with `punctuation` (a language tag), in that language's punctuation (zh-Hant: ，。)."""
    meta = read_meta(video_id)
    if not any(t["id"] == track_id for t in meta.get("tracks", [])) or not track_id.isdigit():
        raise VideoError("No such subtitle track.")
    path = video_folder(video_id) / "subs" / f"{int(track_id):03d}.srt"
    found = parse_subtitles(path.read_text(encoding="utf-8", errors="replace"))
    if punctuation:
        found = [{**c, "text": fullwidth_punctuation(c["text"], punctuation)} for c in found]
    return found


def remove_subtitles(video_id: str, track_id: str) -> list[dict]:
    with lock:
        tracks = read_meta(video_id).get("tracks", [])
        if not any(t["id"] == track_id for t in tracks) or not track_id.isdigit():
            raise VideoError("No such subtitle track.")
        (video_folder(video_id) / "subs" / f"{int(track_id):03d}.srt").unlink(missing_ok=True)
        tracks = [t for t in tracks if t["id"] != track_id]
        update_meta(video_id, tracks=tracks)
        prefs = read_file(video_id, "prefs.json", {})
        for key in ("primary", "secondary"):
            if prefs.get(key) == track_id:
                prefs[key] = ""
        write_file(video_id, "prefs.json", prefs)
        return tracks


def add_embedded_subtitles(video_id: str, source: Path) -> None:
    """Adds every text subtitle track of the video file itself."""
    streams = text_subtitle_streams(source)
    if not streams:
        return
    with tempfile.TemporaryDirectory(prefix="miningcat-subs-") as tmp:
        extract_subtitle_streams(source, streams, Path(tmp))
        for s in streams:
            path = Path(tmp) / f"{s['index']}.srt"
            try:
                if path.is_file() and path.stat().st_size:
                    add_subtitles(video_id, path.name, path.read_bytes(), origin="embedded", label=s["label"])
            except VideoError:
                pass
