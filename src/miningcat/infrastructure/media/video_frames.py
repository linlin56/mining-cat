"""Frames of a video, extracted with ffmpeg: previews of the subtitle area, and the frames read by OCR."""
from pathlib import Path

import ffmpeg

from miningcat.domain.ocr.sampling import OCR_FPS_DEFAULT


def probe_dimensions(video_file: Path) -> tuple[int, int]:
    probe = ffmpeg.probe(str(video_file))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    return int(stream["width"]), int(stream["height"])


def probe_duration(video_file: Path) -> float:
    probe = ffmpeg.probe(str(video_file))
    return float(probe["format"]["duration"])


# Grabs a single frame at a given fraction of the video's duration,
# for the region-selection preview (GUI popup or CLI helper).
def grab_sample_frame(video_file: Path, output_path: Path, at_fraction: float = 0.25) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = probe_duration(video_file) * at_fraction
    (
        ffmpeg
        .input(str(video_file), ss=timestamp)
        .output(str(output_path), vframes=1)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# Spread across the middle of the video (avoiding the very start/end, which are more likely to be black frames, logos, or credits without any dialogue).
DEFAULT_PREVIEW_FRACTIONS: tuple[float, ...] = tuple(i / 11 for i in range(1, 11))


# Grabs several candidate preview frames so the GUI's region-selection dialog can offer a small carousel
# the subtitle-selection frame might land on a moment with no dialogue on screen, having multiple frames helps to avoid that.
def grab_sample_frames(
    video_file: Path, output_dir: Path, fractions: tuple[float, ...] = DEFAULT_PREVIEW_FRACTIONS,
) -> list[Path]:
    return [
        grab_sample_frame(video_file, output_dir / f"preview_{i:02d}.jpg", at_fraction=fraction)
        for i, fraction in enumerate(fractions)
    ]


# Extracts frames already cropped to `region_px`, sampled at `fps` frames per second, directly via ffmpeg filters
# it avoids extracting full frames and cropping them in Python.
# Returns paths sorted by frame index, where frame N (0-indexed) corresponds to timestamp N / fps seconds.
def extract_cropped_frames(
    video_file: Path, output_dir: Path, region_px: tuple[int, int, int, int], fps: int = OCR_FPS_DEFAULT,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    x, y, w, h = region_px
    (
        ffmpeg
        .input(str(video_file))
        .filter("fps", fps=fps)
        .filter("crop", w, h, x, y)
        .output(str(output_dir / "frame_%06d.jpg"), start_number=0, **{"q:v": 2})
        .overwrite_output()
        .run(quiet=True)
    )
    return sorted(output_dir.glob("frame_*.jpg"))
