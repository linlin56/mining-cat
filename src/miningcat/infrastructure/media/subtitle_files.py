"""Subtitle files with ffmpeg: the text subtitle tracks of a video, and .vtt/.ass files converted to SRT."""
import subprocess
import tempfile
from pathlib import Path

import ffmpeg

from miningcat.domain.library.errors import VideoError

# Subtitle codecs that can be turned into SRT (image subtitles, like PGS, can't).
TEXT_SUBTITLE_CODECS = ("subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "subviewer", "realtext")


def text_subtitle_streams(source: Path) -> list[dict]:
    """{"index", "label"} of the text subtitle tracks of a video."""
    try:
        streams = ffmpeg.probe(str(source)).get("streams", [])
    except ffmpeg.Error:
        return []
    subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
    return [{"index": i, "label": (s.get("tags") or {}).get("title") or (s.get("tags") or {}).get("language") or f"Track {i + 1}"}
            for i, s in enumerate(subtitles) if s.get("codec_name") in TEXT_SUBTITLE_CODECS]


def extract_subtitle_streams(source: Path, streams: list[dict], folder: Path) -> None:
    """Writes each stream to folder/<index>.srt, in one read of the file (one ffmpeg output per track): a movie with
    ten tracks isn't read ten times. If ffmpeg fails on one of them, they're extracted one by one."""
    def command(selected):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        for s in selected:
            cmd += ["-map", f"0:s:{s['index']}", "-c:s", "srt", str(folder / f"{s['index']}.srt")]
        return cmd

    if subprocess.run(command(streams), capture_output=True, check=False).returncode != 0:
        for s in streams:
            subprocess.run(command([s]), capture_output=True, check=False)


def convert_to_srt(text: str, ext: str) -> str:
    """Subtitles of another format (vtt, ass, ssa) as SRT."""
    with tempfile.TemporaryDirectory(prefix="miningcat-subs-") as tmp:
        source, target = Path(tmp) / f"in.{ext}", Path(tmp) / "out.srt"
        source.write_text(text, encoding="utf-8")
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), str(target)],
                           capture_output=True, check=True, timeout=60)
        except FileNotFoundError:
            raise VideoError("ffmpeg isn't installed: it's needed to read .vtt and .ass subtitles.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise VideoError("These subtitles can't be read.")
        return target.read_text(encoding="utf-8", errors="replace")
