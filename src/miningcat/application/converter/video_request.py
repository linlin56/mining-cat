from dataclasses import dataclass
from pathlib import Path
from typing import Self

from miningcat.application.converter.errors import ConverterError
from miningcat.domain.languages import Language
from miningcat.domain.ocr.regions import Region, valid_region
from miningcat.domain.ocr.sampling import OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN


@dataclass(frozen=True)
class VideoRequest:
    """What the video pipeline makes subtitles for, and how."""

    language: Language
    url: str | None = None
    video_path: Path | None = None
    model_name: str = "tiny"
    # Instagram's X-IG-App-ID.
    app_id: str = "web"
    # Chinese script the subtitles are converted to.
    convert_target: str | None = None
    # Audio track transcribed when the video has several (0-based).
    audio_track: int | None = None
    # OCR of burned-in subtitles instead of Whisper, in a region of the frame, sampled `ocr_fps` times per second.
    use_ocr: bool = False
    ocr_region: Region | None = None
    ocr_fps: int = OCR_FPS_DEFAULT


class VideoRequestBuilder:
    """Builds a VideoRequest from the user's choices, checking each one:

        VideoRequestBuilder(Language.JAPANESE).local_file(path, audio_track=1).whisper("small").build()
        VideoRequestBuilder(Language.FRENCH).url(url).ocr(region=(0, 0.7, 1, 0.3), fps=6).build()
    """

    def __init__(self, language: Language):
        self._values: dict = {"language": language}

    def url(self, url: str, app_id: str = "web") -> Self:
        url = (url or "").strip()
        if not url:
            raise ConverterError("Enter a video URL.", "Missing URL")
        self._values.update(url=url, video_path=None, app_id=app_id)
        return self

    def local_file(self, path: Path | str, audio_track: int | None = None) -> Self:
        self._values.update(video_path=Path(path), url=None, audio_track=audio_track)
        return self

    def whisper(self, model_name: str) -> Self:
        self._values.update(use_ocr=False, model_name=model_name)
        return self

    def ocr(self, region=None, fps: int | None = None) -> Self:
        """OCR of the subtitles: fps is kept between OCR_FPS_MIN and OCR_FPS_MAX, the region must be valid."""
        try:
            region = valid_region(region) if region is not None else None
        except (TypeError, ValueError):
            raise ConverterError("The subtitle region is invalid.", "Invalid region")
        try:
            fps = int(fps) if fps is not None else OCR_FPS_DEFAULT
        except (TypeError, ValueError):
            fps = OCR_FPS_DEFAULT
        self._values.update(use_ocr=True, ocr_region=region, ocr_fps=max(OCR_FPS_MIN, min(OCR_FPS_MAX, fps)))
        return self

    def convert_to(self, script: str | None) -> Self:
        self._values["convert_target"] = script
        return self

    def build(self) -> VideoRequest:
        if not self._values.get("url") and not self._values.get("video_path"):
            raise ConverterError("Select a local video file or enter a video URL.")
        return VideoRequest(**self._values)
