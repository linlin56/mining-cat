import os
import shutil
import subprocess
from pathlib import Path

import ffmpeg

import video_downloader
from config import AUDIO_BITRATE, DIR_FINAL, DIR_SRT, DIR_TEMP, DIR_VIDEOS
from language import Language


def extract_audio(video_file: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{video_file.stem}.mp3"
    (
        ffmpeg
        .input(str(video_file))
        .output(str(audio_path), acodec="libmp3lame", audio_bitrate=AUDIO_BITRATE, vn=None)
        .overwrite_output()
        .run(quiet=True)
    )
    return audio_path


# Finds a platform-provided subtitle file written alongside the video (e.g. YouTube
# captions downloaded as a side effect of video_downloader.download_video), if any.
def find_platform_subtitle(directory: Path, video_stem: str) -> Path | None:
    matches = sorted(directory.glob(f"{video_stem}.*.srt"))
    return matches[0] if matches else None


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
    url: str,
    model_name: str = "tiny",
    language: Language = Language.MANDARIN_TW,
    app_id: str = "web",
    convert_target: str | None = None,
) -> None:
    import stable_whisper

    import align
    import chinese_converter

    video_file = video_downloader.download_video(
        url, DIR_VIDEOS, app_id=app_id, language=language,
    )

    subtitle_tracks: list[tuple[Path, str]] = []

    DIR_SRT.mkdir(parents=True, exist_ok=True)
    platform_srt = find_platform_subtitle(DIR_VIDEOS, video_file.stem)
    if platform_srt is not None:
        source_srt_file = DIR_SRT / f"{video_file.stem}_source.srt"
        shutil.copy(platform_srt, source_srt_file)
        print(f"Existing subtitles found: {platform_srt.name} -> {source_srt_file}")
        subtitle_tracks.append((source_srt_file, "Source"))

    print("\n=== Extracting audio ===")
    audio_file = extract_audio(video_file, DIR_TEMP)
    print(f"Audio: {audio_file}")

    print(f"\n=== Transcribing (model={model_name}, language={language.name.lower()}) ===")
    model = stable_whisper.load_model(model_name, device=align.get_device())
    segs = align.transcribe_chapter(model, audio_file, lang=language)
    whisper_srt_file = DIR_SRT / f"{video_file.stem}_whisper.srt"
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
