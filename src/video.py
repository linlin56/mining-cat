import os
import shutil
import subprocess
from pathlib import Path

import ffmpeg

import video_downloader
from config import AUDIO_BITRATE, DIR_FINAL, DIR_SRT, DIR_TEMP, DIR_VIDEOS
from language import Language


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
def _sidecar_tag(srt_file: Path, video_stem: str) -> str:
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


# Gathers every subtitle track the input video already came with
def _collect_source_subtitles(video_file: Path) -> list[tuple[Path, str]]:
    sidecars = find_platform_subtitles(video_file.parent, video_file.stem)
    if sidecars:
        return [(p, _sidecar_tag(p, video_file.stem)) for p in sidecars]
    return extract_embedded_subtitles(video_file, DIR_TEMP)


# Mux one or more subtitle tracks into the original video, keeping video/audio streams
# untouched. Each track is (srt_file, title) - the title distinguishes tracks in players
# (e.g. "Source" vs "Whisper") when more than one is embedded.
def mux_subtitles(
    video_file: Path,
    subtitle_tracks: list[tuple[Path, str]],
    output_file: Path,
    subtitle_lang: str = "zho",
) -> bool:
    if not subtitle_tracks:
        return False
    output_file.parent.mkdir(parents=True, exist_ok=True)

    links: list[Path] = []
    for i, (srt_file, _title) in enumerate(subtitle_tracks):
        link = DIR_TEMP / f"video_subs_{i}.srt"
        if link.exists():
            link.unlink()
        try:
            # symlink to fix ffmpeg issues with some paths
            os.symlink(srt_file.absolute(), link.absolute())
        except (OSError, NotImplementedError):
            shutil.copy(srt_file, link)
        links.append(link)

    cmd = ['ffmpeg', '-i', str(video_file)]
    for link in links:
        cmd += ['-i', str(link.absolute())]
    cmd += ['-map', '0:v', '-map', '0:a']
    for i in range(len(links)):
        cmd += ['-map', f'{i + 1}:0']
    cmd += ['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text']
    for i, (_srt_file, title) in enumerate(subtitle_tracks):
        cmd += [f'-metadata:s:s:{i}', f'language={subtitle_lang}']
        cmd += [f'-metadata:s:s:{i}', f'title={title}']
    cmd += ['-y', str(output_file)]

    result = subprocess.run(cmd, check=False)

    for link in links:
        if link.exists():
            link.unlink()

    if result.returncode != 0:
        print(f"  FFmpeg error (code {result.returncode})")
        return False
    return True


def run(
    url: str | None = None,
    model_name: str = "tiny",
    language: Language = Language.MANDARIN_TW,
    app_id: str = "web",
    convert_target: str | None = None,
    video_path: str | Path | None = None,
    audio_track: int | None = None,
) -> None:
    import stable_whisper

    import align
    import chinese_converter

    if video_path is not None:
        video_file = Path(video_path)
        print(f"Using local video: {video_file}")
    else:
        video_file = video_downloader.download_video(
            url, DIR_VIDEOS, app_id=app_id, language=language,
        )

    subtitle_tracks: list[tuple[Path, str]] = []

    DIR_SRT.mkdir(parents=True, exist_ok=True)
    # Looks next to the video file itself - this is where yt-dlp writes platform captions,
    # and also lets a local video reuse any same-stem .srt files sitting alongside it. 
    # Falls back to subtitle streams embedded in the container when there's no sidecar file at all.
    source_subs = _collect_source_subtitles(video_file)
    multiple = len(source_subs) > 1
    for i, (srt_file, tag) in enumerate(source_subs):
        suffix = f"_{i}" if multiple else ""
        source_srt_file = DIR_SRT / f"{video_file.stem}_source{suffix}.srt"
        shutil.copy(srt_file, source_srt_file)
        label = f"Source ({tag})" if multiple else "Source"
        print(f"Existing subtitles found: {srt_file.name} -> {source_srt_file}")
        subtitle_tracks.append((source_srt_file, label))

    print("\n=== Extracting audio ===")
    audio_file = extract_audio(video_file, DIR_TEMP, audio_track=audio_track)
    print(f"Audio: {audio_file}")

    print(f"\n=== Transcribing (model={model_name}, language={language.name.lower()}) ===")
    whisper_srt_file = DIR_SRT / f"{video_file.stem}_whisper.srt"
    if whisper_srt_file.exists():
        print(f"A previous transcription exists and will be overwritten: {whisper_srt_file}")
    model = stable_whisper.load_model(model_name, device=align.get_device())
    segs = align.transcribe_chapter(model, audio_file, lang=language)
    align.save_srt(segs, whisper_srt_file)
    print(f"Subtitles: {whisper_srt_file}  ({len(segs)} segments)")
    subtitle_tracks.append((whisper_srt_file, "Whisper"))

    # Convert script if requested (applies to every SRT in DIR_SRT, source and whisper alike)
    source_script = chinese_converter.SCRIPT_FOR_LANGUAGE.get(language)
    if convert_target is not None and source_script is not None:
        print(f"\n=== Character conversion ({source_script} -> {convert_target}) ===")
        chinese_converter.convert_srt_dir(source_script, convert_target)

    print("\n=== Muxing subtitles into video ===")
    output_file = DIR_FINAL / f"{video_file.stem}.mp4"
    if mux_subtitles(video_file, subtitle_tracks, output_file, subtitle_lang=language.value.iso639_2):
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
