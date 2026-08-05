from pathlib import Path

import ffmpeg

# Normalized (x, y, w, h) fractions of the frame
# bottom third, minimizes OCR noise from on-screen visual content compared to e.g. bottom half.
DEFAULT_REGION: tuple[float, float, float, float] = (0.0, 2 / 3, 1.0, 1 / 3)

# User-adjustable OCR sampling rate range (GUI slider / --ocr-fps CLI flag).
OCR_FPS_MIN = 2
OCR_FPS_MAX = 12
OCR_FPS_DEFAULT = 4


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


# Converts a normalized (x, y, w, h) region (fractions in [0, 1]) to pixel coordinates for the given frame size, clamping so the crop never runs past the frame edges.
def region_to_pixels(
    region: tuple[float, float, float, float], width: int, height: int,
) -> tuple[int, int, int, int]:
    x_frac, y_frac, w_frac, h_frac = region
    x = max(0, min(round(x_frac * width), width))
    y = max(0, min(round(y_frac * height), height))
    w = max(1, min(round(w_frac * width), width - x))
    h = max(1, min(round(h_frac * height), height - y))
    return x, y, w, h


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
