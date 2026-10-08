from pathlib import Path

from miningcat.domain.subtitles.segment import Segment, format_srt
from miningcat.domain.subtitles.srt import srt_text


def save_srt(segments: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_srt(segments), encoding="utf-8")


def srt_file_text(path: Path) -> str:
    """The dialogue of an SRT file, without its numbers and timestamps."""
    return srt_text(path.read_text(encoding="utf-8"))
