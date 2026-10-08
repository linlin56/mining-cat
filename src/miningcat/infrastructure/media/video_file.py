"""Audio and subtitle tracks of video files, with ffmpeg."""
import subprocess
from pathlib import Path

import ffmpeg

from miningcat.infrastructure.media.audio_files import AUDIO_BITRATE
from miningcat.infrastructure.media.ffmpeg_command import FfmpegCommand, link_or_copy


# Skips re-extraction if the mp3 is already sitting in output_dir from a previous run on the
# same video (e.g. re-running after tweaking the language or model). Note: if you re-run with
# a different audio_track than last time, delete the cached mp3 first - it won't be redone
# automatically since we have no record of which track produced it.
def extract_audio(video_file: Path, output_dir: Path, audio_track: int | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{video_file.stem}.mp3"
    if audio_path.exists():
        print(f"Audio already extracted, reusing: {audio_path}")
        return audio_path
    output_kwargs = dict(acodec="libmp3lame", audio_bitrate=AUDIO_BITRATE, vn=None)
    if audio_track is not None:
        output_kwargs["map"] = f"0:a:{audio_track}"
    (
        ffmpeg
        .input(str(video_file))
        .output(str(audio_path), **output_kwargs)
        .overwrite_output()
        .run(quiet=True)
    )
    return audio_path


# Lists the audio streams of a video file so the user can pick which one to transcribe
#  useful when a local video has several audio tracks (e.g. dubs) and the default isn't the wanted language.
def list_audio_tracks(video_file: Path) -> list[dict]:
    try:
        probe = ffmpeg.probe(str(video_file))
    except ffmpeg.Error:
        return []
    tracks = []
    for i, stream in enumerate(s for s in probe.get("streams", []) if s.get("codec_type") == "audio"):
        tags = stream.get("tags", {})
        tracks.append({
            "index": i,
            "language": tags.get("language", ""),
            "title": tags.get("title", ""),
            "channels": stream.get("channels"),
            "codec": stream.get("codec_name"),
        })
    return tracks


# Finds all platform-provided subtitle files written alongside the video (e.g. YouTube
# captions downloaded as a side effect of video_downloader.download_video, one per language).
def find_platform_subtitles(directory: Path, video_stem: str) -> list[Path]:
    return sorted(directory.glob(f"{video_stem}.*.srt"))


# Tag identifying a sidecar subtitle file, e.g. "video.zh-Hant.srt" with stem "video" -> "zh-Hant".
def sidecar_tag(srt_file: Path, video_stem: str) -> str:
    return srt_file.stem[len(video_stem) + 1:]


# Extracts every text-based subtitle stream muxed into the video container itself, e.g. a local .mkv/.mp4 that carries one or more subtitle tracks. 
# Streams that can't be converted to SRT are skipped.
# Returns (path, tag) pairs, tag being the stream's title/language tag if present (falls back to "Track N").
def extract_embedded_subtitles(video_file: Path, output_dir: Path) -> list[tuple[Path, str]]:
    try:
        probe = ffmpeg.probe(str(video_file))
    except ffmpeg.Error:
        return []
    subtitle_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "subtitle"]
    if not subtitle_streams:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Path, str]] = []
    for i, stream in enumerate(subtitle_streams):
        srt_path = output_dir / f"{video_file.stem}_embedded_{i}.srt"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_file), "-map", f"0:s:{i}", str(srt_path)],
            capture_output=True, check=False,
        )
        if result.returncode != 0 or not srt_path.exists() or srt_path.stat().st_size == 0:
            continue
        tags = stream.get("tags", {})
        tag = tags.get("title") or tags.get("language") or f"Track {i}"
        results.append((srt_path, tag))
    return results


def source_subtitles(video_file: Path, scratch_dir: Path) -> list[tuple[Path, str]]:
    """Every subtitle track the video already comes with: its sidecar files, else the tracks of its container."""
    sidecars = find_platform_subtitles(video_file.parent, video_file.stem)
    if sidecars:
        return [(p, sidecar_tag(p, video_file.stem)) for p in sidecars]
    return extract_embedded_subtitles(video_file, scratch_dir)


# Mux one or more subtitle tracks into the original video, keeping video/audio streams
# untouched. Each track is (srt_file, title) - the title distinguishes tracks in players
# (e.g. "Source" vs "Whisper") when more than one is embedded.
def mux_subtitles(
    video_file: Path,
    subtitle_tracks: list[tuple[Path, str]],
    output_file: Path,
    scratch_dir: Path,
    subtitle_lang: str = "zho",
) -> bool:
    """Adds subtitle tracks (srt file, title) to a video, its video and audio streams copied as they are. The title
    tells the tracks apart in players ("Source", "Whisper"...). Returns whether ffmpeg succeeded."""
    if not subtitle_tracks:
        return False
    output_file.parent.mkdir(parents=True, exist_ok=True)
    links = [link_or_copy(srt_file, scratch_dir / f"video_subs_{i}.srt") for i, (srt_file, _) in enumerate(subtitle_tracks)]

    command = FfmpegCommand().input(video_file)
    for link in links:
        command.input(link.absolute())
    command.map("0:v", "0:a", *(f"{i + 1}:0" for i in range(len(links))))
    command.codec("v", "copy").codec("a", "copy").codec("s", "mov_text")
    for i, (_srt_file, title) in enumerate(subtitle_tracks):
        command.metadata(f"s:s:{i}", "language", subtitle_lang).metadata(f"s:s:{i}", "title", title)
    result = subprocess.run(command.overwrite().build(output_file), check=False)

    for link in links:
        link.unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"  FFmpeg error (code {result.returncode})")
        return False
    return True
