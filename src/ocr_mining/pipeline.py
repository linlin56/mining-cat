import shutil
from pathlib import Path

from PIL import Image

from align import Segment
from config import DIR_OCR_FRAMES
from language import Language
from ocr_mining import builder, dedup, frames
from ocr_mining.engine import OcrEngine

# Generates subtitle segments from a video file by extracting frames, performing OCR, and building segments based on the detected text.
def generate_segments(
    video_file: Path,
    language: Language,
    region: tuple[float, float, float, float] | None = None,
    fps: int = 2,
) -> list[Segment]:
    region = region or frames.DEFAULT_REGION
    width, height = frames.probe_dimensions(video_file)
    region_px = frames.region_to_pixels(region, width, height)

    frames_dir = DIR_OCR_FRAMES / video_file.stem
    frame_records: list[tuple[float, str]] = []
    prev_image: Image.Image | None = None
    prev_text = ""

    try:
        # Extract frames cropped to the specified region and sampled at the given FPS, then perform OCR on each frame.
        frame_paths = frames.extract_cropped_frames(video_file, frames_dir, region_px, fps=fps)
        engine = OcrEngine(language)
        for i, frame_path in enumerate(frame_paths):
            image = Image.open(frame_path)
            # If the current frame is visually similar to the previous one, reuse the previous OCR result to avoid redundant processing.
            if prev_image is not None and dedup.frames_are_similar(image, prev_image):
                text = prev_text
            # Otherwise, perform OCR on the current frame and check if the detected text is plausible for the specified language.
            else:
                text = engine.read_text(frame_path)
                if not dedup.is_plausible_text(text, language):
                    text = ""
            frame_records.append((i / fps, text))
            prev_image, prev_text = image, text
            if (i + 1) % 30 == 0 or i == len(frame_paths) - 1:
                print(f"  OCR progress: {i + 1}/{len(frame_paths)} frames")
    finally:
        # Clean up the temporary frames directory after processing to free up disk space.
        shutil.rmtree(frames_dir, ignore_errors=True)
    return builder.build_segments(frame_records, frame_duration=1 / fps)
