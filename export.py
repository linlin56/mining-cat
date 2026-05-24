# export.py — Render final MP4 files.

import os
import shutil
import subprocess
from pathlib import Path

import ffmpeg
from PIL import Image
from tqdm import tqdm

from config import DIR_CHAPTERS_AUDIO, DIR_FINAL, DIR_SRT, DIR_TEMP

# We use a black image for the video.
# TODO later may use the book cover or a simple animated waveform instead.
def create_black_image(width: int = 1920, height: int = 1080) -> Path:
    output_path = DIR_TEMP / "black_frame.png"
    if not output_path.exists():
        img = Image.new('RGB', (width, height), color='black')
        img.save(output_path)
    return output_path


def get_chapter_audio_files() -> list[Path]:
    files = sorted(DIR_CHAPTERS_AUDIO.glob("*.mp3"))
    if not files:
        raise FileNotFoundError(f"No .mp3 found in {DIR_CHAPTERS_AUDIO}")
    return files


def get_audio_duration(audio_file: Path) -> float:
    probe = ffmpeg.probe(str(audio_file))
    return float(probe['format']['duration'])


def export_chapter_to_mp4(
    audio_file: Path,
    black_image: Path,
    output_file: Path,
    preset: str = "ultrafast",
) -> bool:
    srt_file = DIR_SRT / (audio_file.stem + ".srt")
    if not srt_file.exists():
        print(f"  SRT not found: {srt_file}")
        print(f"  Run first: main.py align --only {audio_file.stem}")
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    audio_duration = get_audio_duration(audio_file)

    srt_link = Path("subs.srt")
    if srt_link.exists():
        srt_link.unlink()
    try:
        # Create a symlink to the SRT file in the current directory, to fix ffmpeg issues with some paths
        os.symlink(srt_file.absolute(), srt_link.absolute())
    except (OSError, NotImplementedError):
        shutil.copy(srt_file, srt_link)

    # The ffmpeg command
    cmd = [
        'ffmpeg',
        '-loop', '1', '-framerate', '1', '-i', str(black_image),
        '-i', str(audio_file),
        '-i', str(srt_link.absolute()),
        '-c:v', 'libx264', '-preset', preset, '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k',
        '-c:s', 'mov_text',
        '-metadata:s:s:0', 'language=zho',
        '-t', str(audio_duration),
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
    chapter_num: int | None = None,
    all_chapters: bool = False,
    preset: str = "ultrafast",
) -> None:
    import sys

    if not DIR_CHAPTERS_AUDIO.exists():
        print(f"Error: {DIR_CHAPTERS_AUDIO} not found — run 'audio' first")
        sys.exit(1)

    chapter_files = get_chapter_audio_files()
    black_image = create_black_image()
    DIR_FINAL.mkdir(parents=True, exist_ok=True)

    if all_chapters:
        print(f"Exporting {len(chapter_files)} chapters...\n")
        for i, audio_file in enumerate(tqdm(chapter_files, unit="ch"), start=1):
            output_file = DIR_FINAL / f"chapter_{i:03d}.mp4"
            export_chapter_to_mp4(audio_file, black_image, output_file, preset)
        print(f"\nDone: {DIR_FINAL}/")
    else:
        num = chapter_num or 1
        if num < 1 or num > len(chapter_files):
            print(f"Invalid chapter {num} (1-{len(chapter_files)})")
            sys.exit(1)
        audio_file = chapter_files[num - 1]
        output_file = DIR_FINAL / f"chapter_{num:03d}.mp4"
        print(f"Exporting chapter {num}: {audio_file.name}")
        if export_chapter_to_mp4(audio_file, black_image, output_file, preset):
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
