import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from web import book_audio, books

VIDEO_EXTENSIONS = ("mp4", "mkv", "webm", "mov", "m4v", "avi", "ts", "flv", "wmv", "mpg", "mpeg")
SUBTITLE_EXTENSIONS = ("srt", "vtt", "ass", "ssa")

# What browsers play: anything else gets a copy for the browser, made once.
BROWSER_CONTAINERS = ("mp4", "m4v", "mov", "webm", "mkv")
BROWSER_VIDEO_CODECS = ("h264", "hevc", "vp8", "vp9", "av1")
BROWSER_AUDIO_CODECS = ("aac", "mp3", "opus", "vorbis", "flac")
# Codecs that go into the MP4 copy as they are.
MP4_VIDEO_CODECS = ("h264", "hevc", "vp9", "av1")
MP4_AUDIO_CODECS = ("aac", "mp3", "opus", "flac")

# Escalation when the browser can't play a video: see play_plan().
LEVELS = ("auto", "remux", "encode")
# Encoding settings measured on an Apple M2 with a 1080p HEVC episode: libx264 "superfast" runs at ~12x real time
# (veryfast: ~9x, and the hardware H.264 encoder isn't faster); CRF 23 keeps the file about the size of the original.
# Decoding uses the hardware when there is one.
ENCODE_PRESET = "superfast"
ENCODE_CRF = "23"
ENCODE_MAX_SIZE = 1920
# Subtitle codecs that can be turned into SRT (image subtitles, like PGS, can't).
TEXT_SUBTITLE_CODECS = ("subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "subviewer", "realtext")

# A video's id comes from its size and its first and last bytes: hashing a whole movie would take too long.
FINGERPRINT_BYTES = 4 * 1024 * 1024
THUMB_WIDTH = 480
OFFSET_LIMIT_S = 600

_ASS_TAGS = re.compile(r"\{\\[^}]*\}")
_SPACES = re.compile(r"\s+")


class VideoError(ValueError):
    pass


_lock = threading.RLock()        # meta.json reads and writes
_work_lock = threading.Lock()    # one preparation (ffmpeg) at a time
_preparing: set[str] = set()
_procs: dict[str, subprocess.Popen] = {}
_downloads: dict[str, dict] = {}


def videos_dir() -> Path:
    return books.DIR_LIBRARY / "videos"


def _video_dir(video_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", video_id or ""):
        raise VideoError("Unknown video.")
    return videos_dir() / video_id


def _source(folder: Path) -> Path:
    source = next(folder.glob("source.*"), None)
    if source is None:
        raise VideoError("The video's file is missing from the library.")
    return source


# Background work; replaced by a direct call in the tests.
def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="miningcat-video").start()


# ---------------------------------------------------------------- import

def fingerprint(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as f:
        digest.update(f.read(FINGERPRINT_BYTES))
        if size > FINGERPRINT_BYTES:
            f.seek(max(FINGERPRINT_BYTES, size - FINGERPRINT_BYTES))
            digest.update(f.read())
    return digest.hexdigest()[:16]


def _extension(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in VIDEO_EXTENSIONS:
        raise VideoError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(VIDEO_EXTENSIONS)})")
    return ext


def import_stream(filename: str, stream, language: str | None = None) -> dict:
    """Imports an uploaded video, written straight to the library as it arrives (a movie doesn't fit in memory)."""
    ext = _extension(filename)
    videos_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=f".{ext}", dir=videos_dir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(stream, out, 1024 * 1024)
        if tmp.stat().st_size == 0:
            raise VideoError("The file is empty.")
        return _add(tmp, ext, Path(filename).name, move=True, language=language)
    finally:
        tmp.unlink(missing_ok=True)


def import_file(path: Path, title: str | None = None, language: str | None = None,
                subtitles: list[tuple[Path, str]] = ()) -> dict:
    """Imports a video already on disk (a download, a conversion), hard-linked when possible.
    `subtitles`: (file, label) pairs, e.g. the captions downloaded with an online video."""
    meta = _add(path, _extension(path.name), path.name, move=False, title=title, language=language)
    for sub, label in subtitles:
        try:
            add_subtitles(meta["id"], sub.name, sub.read_bytes(), origin="platform", label=label)
        except (VideoError, OSError):
            pass  # a broken caption file mustn't lose the video
    return get_meta(meta["id"])


def _link_or_copy(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _add(file: Path, ext: str, filename: str, move: bool, title: str | None = None, language: str | None = None) -> dict:
    video_id = fingerprint(file)
    folder = _video_dir(video_id)
    with _lock:
        if (folder / "meta.json").exists():
            return get_meta(video_id)
        shutil.rmtree(folder, ignore_errors=True)  # leftovers of an interrupted import
        folder.mkdir(parents=True)
        target = folder / f"source.{ext}"
        if move:
            file.replace(target)
        else:
            _link_or_copy(file, target)
        if language:
            books._write_json(folder / "prefs.json", {"language": language})
        books._write_json(folder / "meta.json", {
            "id": video_id, "filename": filename, "title": title or Path(filename).stem,
            "added": time.time(), "status": "queued", "progress": 0, "error": None, "tracks": [],
        })
        start_prepare(video_id)
    return get_meta(video_id)


# ---------------------------------------------------------------- metadata

def _update(video_id: str, **changes) -> dict:
    with _lock:
        path = _video_dir(video_id) / "meta.json"
        meta = books._read_json(path, None)
        if meta is None:
            raise VideoError("Unknown video.")
        meta.update(changes)
        books._write_json(path, meta)
        return meta


def get_meta(video_id: str) -> dict:
    with _lock:
        meta = books._read_json(_video_dir(video_id) / "meta.json", None)
        if meta is None:
            raise VideoError("Unknown video.")
        # interrupted by a restart of MiningCat: prepare it again
        if meta.get("status") in ("queued", "preparing") and video_id not in _preparing:
            start_prepare(video_id)
            meta = books._read_json(_video_dir(video_id) / "meta.json", meta)
        return meta


def list_videos() -> list[dict]:
    if not videos_dir().exists():
        return []
    videos = []
    for folder in videos_dir().iterdir():
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
    folder = _video_dir(video_id)
    meta = get_meta(video_id)
    if meta.get("status") != "ready":
        raise VideoError("The video isn't ready yet.")
    play = folder / "play.mp4"
    return play if play.exists() else _source(folder)


def thumb_path(video_id: str) -> Path:
    path = _video_dir(video_id) / "thumb.jpg"
    if not path.is_file():
        raise VideoError("No thumbnail.")
    return path


def delete_video(video_id: str) -> None:
    folder = _video_dir(video_id)
    with _lock:
        proc = _procs.get(video_id)
        if proc is not None:
            proc.kill()
        if folder.exists():
            shutil.rmtree(folder)


# ---------------------------------------------------------------- preparation

def probe(path: Path) -> dict:
    import ffmpeg

    try:
        data = ffmpeg.probe(str(path))
    except FileNotFoundError:
        raise VideoError("ffmpeg isn't installed: it's needed to read videos.")
    except ffmpeg.Error as exc:
        raise VideoError(f"This file can't be read as a video: {exc.stderr.decode(errors='replace').strip()[-300:]}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    return {
        "duration": round(duration, 3),
        "video_codec": video.get("codec_name") if video else None,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "pix_fmt": video.get("pix_fmt") if video else None,
        "audio": [{
            "index": i, "codec": s.get("codec_name"), "channels": s.get("channels"),
            "language": (s.get("tags") or {}).get("language", ""), "title": (s.get("tags") or {}).get("title", ""),
        } for i, s in enumerate(audio)],
    }


def play_plan(ext: str, info: dict, audio_track: int = 0, level: str = "auto") -> dict | None:
    """How to make the copy for the browser, or None when the original plays as it is. The browser asks for more
    when it can't play what it got (see LEVELS): "remux" puts the streams as they are in an MP4 (a second or two:
    e.g. Safari plays HEVC, but not in MKV), "encode" encodes the video again (minutes: browsers without HEVC)."""
    audio = info["audio"]
    audio_track = audio_track if 0 <= audio_track < len(audio) else 0
    vcodec = info["video_codec"]
    acodec = audio[audio_track]["codec"] if audio else None
    if (level == "auto" and ext in BROWSER_CONTAINERS and audio_track == 0
            and (vcodec is None or vcodec in BROWSER_VIDEO_CODECS)
            and (acodec is None or acodec in BROWSER_AUDIO_CODECS)):
        return None
    encode = vcodec is not None and (level == "encode" or vcodec not in MP4_VIDEO_CODECS)
    return {
        "video": None if vcodec is None else "h264" if encode else "copy",
        "audio": None if acodec is None else "copy" if acodec in MP4_AUDIO_CODECS else "aac",
        "audio_track": audio_track if audio else None,
        "hevc": vcodec == "hevc",
        # 4K and more is brought down to 1080p: much faster to encode, and enough for a screenshot
        "scale": encode and max(info.get("width") or 0, info.get("height") or 0) > ENCODE_MAX_SIZE,
    }


def _ffmpeg_command(source: Path, target: Path, plan: dict) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-y"]
    if plan["video"] == "h264":
        cmd += ["-hwaccel", "auto"]  # hardware decoding when available, else ffmpeg decodes as usual
    cmd += ["-i", str(source)]
    if plan["video"]:
        cmd += ["-map", "0:V:0"]
        if plan["video"] == "copy":
            cmd += ["-c:v", "copy"] + (["-tag:v", "hvc1"] if plan["hevc"] else [])
        else:
            if plan.get("scale"):
                size = ENCODE_MAX_SIZE
                cmd += ["-vf", f"scale='if(gte(iw,ih),min({size},iw),-2)':'if(gte(iw,ih),-2,min({size},ih))'"]
            cmd += ["-c:v", "libx264", "-preset", ENCODE_PRESET, "-crf", ENCODE_CRF, "-pix_fmt", "yuv420p"]
    if plan["audio"]:
        cmd += ["-map", f"0:a:{plan['audio_track']}"]
        cmd += ["-c:a", "copy"] if plan["audio"] == "copy" else ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    return cmd + ["-sn", "-dn", "-movflags", "+faststart", "-f", "mp4", str(target)]


def _convert(video_id: str, source: Path, target: Path, plan: dict, duration: float) -> None:
    tmp = target.with_name("play.tmp.mp4")
    try:
        proc = subprocess.Popen(_ffmpeg_command(source, tmp, plan), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace")
    except FileNotFoundError:
        raise VideoError("ffmpeg isn't installed: it's needed to prepare videos.")
    _procs[video_id] = proc
    try:
        started = last = time.time()
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and value.isdigit() and duration > 0 and time.time() - last > 1:
                last = time.time()
                done = min(0.99, int(value) / 1e6 / duration)
                eta = round((last - started) * (1 - done) / done) if done > 0.01 else None
                _update(video_id, progress=round(done * 100, 1), eta=eta)
        error = proc.stderr.read()
        if proc.wait() != 0:
            raise VideoError(f"ffmpeg couldn't convert the video: {error.strip()[-300:] or 'stopped'}")
        tmp.replace(target)
    finally:
        _procs.pop(video_id, None)
        tmp.unlink(missing_ok=True)


def _thumbnail(source: Path, target: Path, duration: float) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{duration * 0.1:.2f}", "-i", str(source),
         "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", str(target)],
        capture_output=True, check=False, timeout=60,
    )


def start_prepare(video_id: str, level: str | None = None) -> None:
    """Prepares the video (again). `level`: see play_plan(); by default, the one the video already needed."""
    if level is not None and level not in LEVELS:
        raise VideoError(f"Unknown preparation: {level!r}")
    with _lock:
        if video_id in _preparing:
            raise VideoError("This video is already being prepared.")
        _preparing.add(video_id)
        try:
            _update(video_id, status="queued", progress=0, error=None, eta=None)
        except VideoError:
            _preparing.discard(video_id)
            raise
    _spawn(_prepare, video_id, level)


def _prepare(video_id: str, level: str | None = None) -> None:
    try:
        with _work_lock:
            folder = _video_dir(video_id)
            source = _source(folder)
            meta = _update(video_id, status="preparing", progress=0, step="reading")
            level = level or meta.get("level") or "auto"
            info = probe(source)
            if not meta.get("probed"):
                _update(video_id, **info, step="subtitles")
                _add_embedded_subtitles(video_id, source)
                if info["video_codec"]:
                    _update(video_id, step="thumbnail")
                    _thumbnail(source, folder / "thumb.jpg", info["duration"])
                meta = _update(video_id, probed=True)
            audio_track = get_prefs(video_id).get("audio_track", 0)
            plan = play_plan(source.suffix.lower().lstrip("."), info, audio_track, level)
            play = folder / "play.mp4"
            if plan is None:
                play.unlink(missing_ok=True)
            elif not (play.exists() and meta.get("play_plan") == plan):
                _update(video_id, step="encoding" if plan["video"] == "h264" else "remuxing")
                _convert(video_id, source, play, plan, info["duration"])
            if not meta.get("language"):
                meta = _update(video_id, language=_detect_language(video_id, meta))
            _update(video_id, status="ready", progress=100, error=None, eta=None, step=None, play_plan=plan, level=level)
    except (VideoError, OSError, subprocess.SubprocessError) as exc:
        try:
            _update(video_id, status="error", error=str(exc))
        except (VideoError, OSError):
            pass  # deleted in the meantime
    finally:
        _preparing.discard(video_id)


def _subtitle_streams(source: Path) -> list[dict]:
    import ffmpeg

    try:
        streams = ffmpeg.probe(str(source)).get("streams", [])
    except ffmpeg.Error:
        return []
    subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
    return [{"index": i, "label": (s.get("tags") or {}).get("title") or (s.get("tags") or {}).get("language") or f"Track {i + 1}"}
            for i, s in enumerate(subtitles) if s.get("codec_name") in TEXT_SUBTITLE_CODECS]


# Every text subtitle track of the file, in one read of the file (one ffmpeg output per track): a movie with ten tracks
# isn't read ten times. If ffmpeg fails on one of them, they're extracted one by one.
def _add_embedded_subtitles(video_id: str, source: Path) -> None:
    streams = _subtitle_streams(source)
    if not streams:
        return
    with tempfile.TemporaryDirectory(prefix="miningcat-subs-") as tmp:
        def command(selected):
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
            for s in selected:
                cmd += ["-map", f"0:s:{s['index']}", "-c:s", "srt", str(Path(tmp) / f"{s['index']}.srt")]
            return cmd

        if subprocess.run(command(streams), capture_output=True, check=False).returncode != 0:
            for s in streams:
                subprocess.run(command([s]), capture_output=True, check=False)
        for s in streams:
            path = Path(tmp) / f"{s['index']}.srt"
            try:
                if path.is_file() and path.stat().st_size:
                    add_subtitles(video_id, path.name, path.read_bytes(), origin="embedded", label=s["label"])
            except VideoError:
                pass


def _detect_language(video_id: str, meta: dict) -> str | None:
    for track in meta.get("tracks", []):
        text = " ".join(c["text"] for c in cues(video_id, track["id"])[:400])
        language = books.detect_language(text)
        if language:
            return language
    return None


def audio_tracks(meta: dict) -> list[dict]:
    from web.options import audio_track_label
    return [{"index": t["index"], "label": audio_track_label(t)} for t in meta.get("audio", [])]


# ---------------------------------------------------------------- subtitles

def _clean(text: str) -> str:
    return _SPACES.sub(" ", _ASS_TAGS.sub("", text)).strip()


def parse_subtitles(text: str) -> list[dict]:
    cues = [{"start": round(c.start, 3), "end": round(c.end, 3), "text": _clean(c.text)}
            for c in book_audio.parse_srt(text)]
    return sorted((c for c in cues if c["text"] and c["end"] > c["start"]), key=lambda c: c["start"])


def _to_srt(data: bytes, ext: str) -> str:
    if ext == "srt":
        return books.decode_text(data)
    with tempfile.TemporaryDirectory(prefix="miningcat-subs-") as tmp:
        source, target = Path(tmp) / f"in.{ext}", Path(tmp) / "out.srt"
        source.write_text(books.decode_text(data), encoding="utf-8")
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), str(target)],
                           capture_output=True, check=True, timeout=60)
        except FileNotFoundError:
            raise VideoError("ffmpeg isn't installed: it's needed to read .vtt and .ass subtitles.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise VideoError("These subtitles can't be read.")
        return target.read_text(encoding="utf-8", errors="replace")


def add_subtitles(video_id: str, filename: str, data: bytes, origin: str = "file", label: str | None = None) -> dict:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in SUBTITLE_EXTENSIONS:
        raise VideoError(f"Unsupported subtitles: .{ext or '?'} (supported: {', '.join(SUBTITLE_EXTENSIONS)})")
    text = _to_srt(data, ext)
    found = parse_subtitles(text)
    if not found:
        raise VideoError(f"No subtitles found in {filename}.")
    digest = hashlib.sha256("\n".join(f"{c['start']} {c['text']}" for c in found).encode()).hexdigest()[:16]
    folder = _video_dir(video_id)
    with _lock:
        tracks = get_meta(video_id).get("tracks", [])
        same = next((t for t in tracks if t.get("sha") == digest), None)
        if same:
            return same
        number = 1 + max((int(t["id"]) for t in tracks), default=0)
        (folder / "subs").mkdir(exist_ok=True)
        (folder / "subs" / f"{number:03d}.srt").write_text(text, encoding="utf-8")
        track = {"id": str(number), "label": label or Path(filename).stem, "origin": origin,
                 "cues": len(found), "sha": digest}
        _update(video_id, tracks=[*tracks, track])
    return track


def cues(video_id: str, track_id: str) -> list[dict]:
    meta = get_meta(video_id)
    if not any(t["id"] == track_id for t in meta.get("tracks", [])) or not track_id.isdigit():
        raise VideoError("No such subtitle track.")
    path = _video_dir(video_id) / "subs" / f"{int(track_id):03d}.srt"
    return parse_subtitles(path.read_text(encoding="utf-8", errors="replace"))


def remove_subtitles(video_id: str, track_id: str) -> list[dict]:
    with _lock:
        tracks = get_meta(video_id).get("tracks", [])
        if not any(t["id"] == track_id for t in tracks) or not track_id.isdigit():
            raise VideoError("No such subtitle track.")
        (_video_dir(video_id) / "subs" / f"{int(track_id):03d}.srt").unlink(missing_ok=True)
        tracks = [t for t in tracks if t["id"] != track_id]
        _update(video_id, tracks=tracks)
        prefs = get_prefs(video_id)
        for key in ("primary", "secondary"):
            if prefs.get(key) == track_id:
                prefs[key] = ""
        books._write_json(_video_dir(video_id) / "prefs.json", prefs)
        return tracks


def clip(video_id: str, start, end) -> bytes:
    """The audio of one or more subtitle lines as MP3, with the margins of the settings, cut from the file the browser
    plays (its first audio stream is the chosen track)."""
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        raise VideoError("Invalid time span.")
    settings = get_settings()
    try:
        return book_audio.cut_mp3(file_path(video_id), start, end,
                                  before=settings["audio_before"] / 1000, after=settings["audio_after"] / 1000)
    except book_audio.AudioError as exc:
        raise VideoError(str(exc))


SCREENSHOT_MAX_WIDTH = 1280


def frame(video_id: str, position) -> bytes:
    """The picture at `position` (seconds) as JPEG, for the card of a line that isn't on screen. Grabbing it in the
    browser needs a second, hidden <video>, which Safari doesn't load reliably."""
    try:
        position = max(0.0, float(position))
    except (TypeError, ValueError):
        raise VideoError("Invalid position.")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{position:.3f}", "-i", str(file_path(video_id)),
             "-frames:v", "1", "-vf", f"scale='min({SCREENSHOT_MAX_WIDTH},iw)':-2", "-c:v", "mjpeg", "-q:v", "3",
             "-f", "image2pipe", "pipe:1"],
            capture_output=True, check=True, timeout=30,
        )
    except FileNotFoundError:
        raise VideoError("ffmpeg isn't installed: it's needed for screenshots.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise VideoError("ffmpeg couldn't take the screenshot.")
    if not result.stdout:
        raise VideoError("There's no picture at this time.")
    return result.stdout


# ---------------------------------------------------------------- progress, preferences, settings

def get_progress(video_id: str) -> dict:
    return books._read_json(_video_dir(video_id) / "progress.json", {})


def save_progress(video_id: str, position) -> dict:
    meta = get_meta(video_id)
    try:
        position = max(0.0, float(position))
    except (TypeError, ValueError):
        raise VideoError("Invalid position.")
    duration = meta.get("duration") or 0
    percent = min(100.0, position / duration * 100) if duration else 0
    progress = {"time": round(position, 2), "percent": round(percent, 2), "updated": time.time()}
    books._write_json(_video_dir(video_id) / "progress.json", progress)
    return progress


def get_prefs(video_id: str) -> dict:
    return books._read_json(_video_dir(video_id) / "prefs.json", {})


def save_prefs(video_id: str, values: dict) -> dict:
    meta = get_meta(video_id)
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
    books._write_json(_video_dir(video_id) / "prefs.json", prefs)
    return prefs


DEFAULT_SETTINGS = {
    "sub_size": 34,            # px, subtitles over the video
    "sub_display": "shown",    # "shown", "blur" (until hovered) or "hidden"
    "auto_pause": False,       # pause at the end of every subtitle
    "colors": "status",        # words coloured by status, or "off"
    "list": True,              # subtitle list next to the video
    "audio_before": 200,       # ms of audio kept before and after a line, on cards
    "audio_after": 200,
}
AUDIO_MARGIN_MAX_MS = 3000
_CHOICES = {"sub_display": ("shown", "blur", "hidden"), "colors": ("status", "off")}


def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **books._read_json(books.DIR_LIBRARY / "player_settings.json", {})}


def save_settings(values: dict) -> dict:
    settings = get_settings()
    for key, default in DEFAULT_SETTINGS.items():
        if key not in values:
            continue
        value = values[key]
        if isinstance(default, bool):
            settings[key] = bool(value)
        elif key in ("sub_size", "audio_before", "audio_after"):
            low, high = (14, 80) if key == "sub_size" else (0, AUDIO_MARGIN_MAX_MS)
            try:
                settings[key] = max(low, min(high, int(value)))
            except (TypeError, ValueError):
                continue
        elif value in _CHOICES[key]:
            settings[key] = value
    books._write_json(books.DIR_LIBRARY / "player_settings.json", settings)
    return settings


# ---------------------------------------------------------------- online videos

def start_download(url: str, language, tag: str | None = None) -> dict:
    """Downloads an online video with the converter's platform handlers (YouTube captions included), then imports it."""
    job = {"id": secrets.token_hex(6), "url": url, "status": "downloading", "error": None, "video": None}
    _downloads[job["id"]] = job
    started = dict(job)
    _spawn(_download, job, language, tag)
    return started


def _online_title(url: str) -> str | None:
    try:
        import yt_dlp
        from video_handlers._common import BASE_YDL_OPTS
        with yt_dlp.YoutubeDL(BASE_YDL_OPTS) as ydl:
            return ydl.extract_info(url, download=False).get("title")
    except Exception:
        return None


# `tag`: the video's language tag when `language` (the converter's, for YouTube captions) isn't given.
def _download(job: dict, language, tag: str | None = None) -> None:
    try:
        import video
        import video_downloader
        from config import DIR_VIDEOS
        from web.game import language_tag

        path = video_downloader.download_video(job["url"], DIR_VIDEOS, app_id="web", language=language)
        subtitles = [(p, video._sidecar_tag(p, path.stem)) for p in video.find_platform_subtitles(path.parent, path.stem)]
        meta = import_file(path, title=_online_title(job["url"]), language=language_tag(language) if language else tag,
                           subtitles=subtitles)
        job.update(status="done", video=meta["id"])
    except Exception as exc:
        job.update(status="error", error=str(exc) or type(exc).__name__)


def downloads() -> list[dict]:
    return [dict(j) for j in _downloads.values() if j["status"] != "done"]


def dismiss_download(job_id: str) -> None:
    job = _downloads.get(job_id)
    if job and job["status"] != "downloading":
        del _downloads[job_id]
