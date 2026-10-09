import json
import subprocess
from pathlib import Path

import ffmpeg

from miningcat.domain.audiobook.chapter import Chapter
from miningcat.infrastructure.media.audio_files import AUDIO_BITRATE, AUDIO_FORMAT


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
