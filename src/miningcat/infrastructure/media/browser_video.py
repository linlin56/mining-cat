"""Videos for the browser, with ffmpeg: what a video holds, how to make a copy the browser can play, thumbnails and
screenshots."""
import subprocess
import time
from pathlib import Path
from typing import Callable

import ffmpeg

from miningcat.domain.library.errors import VideoError

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


THUMB_WIDTH = 480


def probe(path: Path) -> dict:
    """Duration, video codec and size, and audio tracks of a video."""
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


def ffmpeg_command(source: Path, target: Path, plan: dict) -> list[str]:
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


def thumbnail(source: Path, target: Path, duration: float) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{duration * 0.1:.2f}", "-i", str(source),
         "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", str(target)],
        capture_output=True, check=False, timeout=60,
    )


def transcode(source: Path, target: Path, plan: dict, duration: float,
              on_start: Callable[[subprocess.Popen], None], on_progress: Callable[[float, int | None], None]) -> None:
    """Makes the browser's copy of a video, following a play_plan(). `on_progress(percent, seconds left)` is called
    about every second."""
    tmp = target.with_name("play.tmp.mp4")
    try:
        proc = subprocess.Popen(ffmpeg_command(source, tmp, plan), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, errors="replace")
    except FileNotFoundError:
        raise VideoError("ffmpeg isn't installed: it's needed to prepare videos.")
    on_start(proc)
    try:
        started = last = time.time()
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and value.isdigit() and duration > 0 and time.time() - last > 1:
                last = time.time()
                done = min(0.99, int(value) / 1e6 / duration)
                eta = round((last - started) * (1 - done) / done) if done > 0.01 else None
                on_progress(round(done * 100, 1), eta)
        error = proc.stderr.read()
        if proc.wait() != 0:
            raise VideoError(f"ffmpeg couldn't convert the video: {error.strip()[-300:] or 'stopped'}")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def grab_frame(video: Path, position: float, max_width: int) -> bytes:
    """The picture at `position` (seconds) as JPEG, at most max_width wide."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{position:.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale='min({max_width},iw)':-2", "-c:v", "mjpeg", "-q:v", "3",
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
