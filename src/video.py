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


# Mux a subtitle track into the original video, keeping video/audio streams untouched.
def mux_subtitles(
    video_file: Path,
    srt_file: Path,
    output_file: Path,
    subtitle_lang: str = "zho",
) -> bool:
    output_file.parent.mkdir(parents=True, exist_ok=True)

    srt_link = DIR_TEMP / "video_subs.srt"
    if srt_link.exists():
        srt_link.unlink()
    try:
        # symlink to fix ffmpeg issues with some paths
        os.symlink(srt_file.absolute(), srt_link.absolute())
    except (OSError, NotImplementedError):
        shutil.copy(srt_file, srt_link)

    cmd = [
        'ffmpeg',
        '-i', str(video_file),
        '-i', str(srt_link.absolute()),
        '-map', '0:v', '-map', '0:a', '-map', '1:0',
        '-c:v', 'copy', '-c:a', 'copy',
        '-c:s', 'mov_text',
        '-metadata:s:s:0', f'language={subtitle_lang}',
        '-y',
        str(output_file),
    ]

    result = subprocess.run(cmd, check=False)

    if srt_link.exists():
        srt_link.unlink()

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

    video_file = video_downloader.download_video(url, DIR_VIDEOS, app_id=app_id)

    print("\n=== Extracting audio ===")
    audio_file = extract_audio(video_file, DIR_TEMP)
    print(f"Audio: {audio_file}")

    print(f"\n=== Transcribing (model={model_name}, language={language.name.lower()}) ===")
    model = stable_whisper.load_model(model_name, device=align.get_device())
    segs = align.transcribe_chapter(model, audio_file, lang=language)
    DIR_SRT.mkdir(parents=True, exist_ok=True)
    srt_file = DIR_SRT / f"{video_file.stem}.srt"
    align.save_srt(segs, srt_file)
    print(f"Subtitles: {srt_file}  ({len(segs)} segments)")

    # Convert script if requested
    source_script = chinese_converter.SCRIPT_FOR_LANGUAGE.get(language)
    if convert_target is not None and source_script is not None:
        print(f"\n=== Character conversion ({source_script} -> {convert_target}) ===")
        chinese_converter.convert_srt_dir(source_script, convert_target)

    print("\n=== Muxing subtitles into video ===")
    output_file = DIR_FINAL / f"{video_file.stem}.mp4"
    if mux_subtitles(video_file, srt_file, output_file, subtitle_lang=language.value.iso639_2):
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
