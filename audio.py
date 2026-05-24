# audio.py — Audio chapter extraction.

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import ffmpeg
from tqdm import tqdm

from config import AUDIO_BITRATE, AUDIO_FORMAT, DIR_AUDIOBOOK, DIR_CHAPTERS_AUDIO, DIR_TEMP


@dataclass
class Chapter:
    index: int
    title: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def start_str(self) -> str:
        return _seconds_to_hhmmss(self.start_time)

    @property
    def end_str(self) -> str:
        return _seconds_to_hhmmss(self.end_time)

    # A slug for the chapter, used in filenames. It includes the index and a sanitized version of the title.
    @property
    def slug(self) -> str:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.title)
        safe = safe.strip().replace(" ", "_")
        return f"{self.index:03d}_{safe}"


def _seconds_to_hhmmss(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def get_audiobook_file() -> Path:
    files = sorted(DIR_AUDIOBOOK.glob("*.m4b"))
    if not files:
        raise FileNotFoundError(f"No .m4b file found in {DIR_AUDIOBOOK}")
    if len(files) > 1:
        print(f"Warning: multiple .m4b files found, using: {files[0].name}")
    return files[0]

# Probe chapters from the .m4b file using ffprobe, returning a list of Chapter objects.
def probe_chapters(m4b_path: Path) -> list[Chapter]:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_chapters",
        str(m4b_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")

    data = json.loads(result.stdout)
    raw_chapters = data.get("chapters", [])

    if not raw_chapters:
        print("No chapters found in file. Make sure your .m4b has chapter markers.")
        return []

    chapters = []
    for i, ch in enumerate(raw_chapters):
        title = ch.get("tags", {}).get("title", f"Chapter {i + 1}")
        start = float(ch["start_time"])
        end   = float(ch["end_time"])
        chapters.append(Chapter(index=i + 1, title=title, start_time=start, end_time=end))
    return chapters


def print_chapters(chapters: list[Chapter], m4b_path: Path) -> None:
    total = sum(c.duration for c in chapters)
    print(f"\nFile     : {m4b_path.name}")
    print(f"Chapters : {len(chapters)}")
    print(f"Total    : {_seconds_to_hhmmss(total)}\n")
    print(f"  {'#':>4}  {'Start':>10}  {'End':>10}  {'Duration':>10}  Title")
    print("  " + "-" * 70)
    for c in chapters:
        dur = _seconds_to_hhmmss(c.duration)
        print(f"  {c.index:>4}  {c.start_str:>10}  {c.end_str:>10}  {dur:>10}  {c.title}")
    print()


def save_chapters_json(chapters: list[Chapter], output_dir: Path) -> Path:
    data = [
        {"index": c.index, "title": c.title, "start_time": c.start_time,
         "end_time": c.end_time, "slug": c.slug}
        for c in chapters
    ]
    out = output_dir / "chapters.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Chapters saved: {out}")
    return out

# Extract a single chapter's audio from the .m4b file using ffmpeg, saving it as an .mp3 in the output directory.
def extract_chapter(m4b_path: Path, chapter: Chapter, output_dir: Path) -> Path:
    out_path = output_dir / f"{chapter.slug}.{AUDIO_FORMAT}"
    if out_path.exists():
        return out_path
    (
        ffmpeg
        .input(str(m4b_path), ss=chapter.start_time, to=chapter.end_time)
        .output(str(out_path), acodec="libmp3lame", audio_bitrate=AUDIO_BITRATE, vn=None)
        .overwrite_output()
        .run(quiet=True)
    )
    return out_path

# Extract all chapters from the .m4b file, returning a list of paths to the extracted audio files.
def extract_all_chapters(
    m4b_path: Path,
    chapters: list[Chapter],
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    print(f"Extracting {len(chapters)} chapters to {output_dir}/\n")
    for chapter in tqdm(chapters, unit="chapter"):
        path = extract_chapter(m4b_path, chapter, output_dir)
        extracted.append(path)
    return extracted

# If multiple .mp3 files are found in the audiobook directory, we treat each as a chapter and copy them to the output directory.
def copy_mp3_chapters(mp3_files: list[Path], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    print(f"{len(mp3_files)} MP3 files found — multi-chapter mode\n")
    for src in mp3_files:
        dst = output_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"  Copied: {src.name}")
        else:
            print(f"  Already present: {src.name}")
        copied.append(dst)
    return copied

# Main function to run the audio processing, detecting the mode and extracting chapters as needed.
def run(dry_run: bool = False) -> None:
    from config import detect_audio_mode
    import sys

    try:
        mode, audio_files = detect_audio_mode()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if mode == "multi_mp3":
        print(f"Mode: multi-MP3 ({len(audio_files)} files = {len(audio_files)} chapters)")
        for f in audio_files:
            print(f"  {f.name}")
        print()
        if dry_run:
            print("Dry-run: no files copied.")
            return
        copied = copy_mp3_chapters(audio_files, DIR_CHAPTERS_AUDIO)
        print(f"\n{len(copied)} chapters ready in {DIR_CHAPTERS_AUDIO}/")
        return

    # TODO: support single .mp3 with chapter splitting (not yet implemented)
    if mode == "single_mp3":
        print("Error: single .mp3 found.")
        print("  Splitting a single .mp3 by chapter is not yet supported.")
        print("  Use a .m4b with chapter markers, or provide multiple .mp3 files.")
        sys.exit(1)

    m4b_path = audio_files[0]
    print(f"Analysing {m4b_path.name} ...")
    chapters = probe_chapters(m4b_path)
    if not chapters:
        sys.exit(1)

    print_chapters(chapters, m4b_path)
    if dry_run:
        print("Dry-run: no files extracted.")
        return

    # Save chapter metadata to JSON for later use, then extract audio for all chapters.
    DIR_TEMP.mkdir(parents=True, exist_ok=True)
    save_chapters_json(chapters, DIR_TEMP)
    extracted = extract_all_chapters(m4b_path, chapters, DIR_CHAPTERS_AUDIO)
    print(f"\n{len(extracted)} chapters extracted to {DIR_CHAPTERS_AUDIO}/")
