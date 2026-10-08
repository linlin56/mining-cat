"""The video pipeline: a video (downloaded or local) gets its subtitles, then all its subtitle tracks are added to it
in output/final."""
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from miningcat.application.converter import speech_engines, transcription
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.ocr_subtitles import generate_segments
from miningcat.application.converter.steps.script_conversion import convert_srt_dir, normalize_whisper_script
from miningcat.application.converter.video_download import download_video
from miningcat.application.converter.video_request import VideoRequest
from miningcat.config.paths import paths
from miningcat.infrastructure.files.srt_files import save_srt
from miningcat.infrastructure.media.video_file import extract_audio, mux_subtitles, source_subtitles

# (SRT file, title of the track in players)
Track = tuple[Path, str]


class SubtitleMaker(ABC):
    """How the pipeline makes subtitles of its own for a video."""

    def __init__(self, request: VideoRequest):
        self.request = request

    @abstractmethod
    def make(self, video_file: Path) -> Track | None:
        """Writes the subtitles of the video to output/srt. Returns their track, None when nothing came out."""


class OcrSubtitles(SubtitleMaker):
    """The subtitles burned into the video, read by OCR."""

    def make(self, video_file: Path) -> Track | None:
        request = self.request
        print(f"\n=== OCR (hardsubs, language={request.language.id}) ===")
        srt_file = paths.srt / f"{video_file.stem}_ocr.srt"
        segs = generate_segments(video_file, language=request.language, region=request.ocr_region, fps=request.ocr_fps)
        save_srt(segs, srt_file)
        print(f"Subtitles: {srt_file}  ({len(segs)} segments)")
        if not segs:
            print("  No subtitles read: check the subtitle region and the language.")
            return None
        return srt_file, "OCR"


class SpeechSubtitles(SubtitleMaker):
    """The speech of the video, transcribed by Whisper (or the language's own engine: Qwen3-ASR for Taigi)."""

    def make(self, video_file: Path) -> Track | None:
        request = self.request
        print("\n=== Extracting audio ===")
        audio_file = extract_audio(video_file, paths.temp, audio_track=request.audio_track)
        print(f"Audio: {audio_file}")

        print(f"\n=== Transcribing (model={request.model_name}, language={request.language.id}) ===")
        srt_file = paths.srt / f"{video_file.stem}_whisper.srt"
        if srt_file.exists():
            print(f"A previous transcription exists and will be overwritten: {srt_file}")
        transcriber = speech_engines.load_transcriber(request.model_name, request.language)
        segs = transcription.transcribe(transcriber, audio_file, request.language)
        save_srt(segs, srt_file)
        normalize_whisper_script(srt_file, request.language)
        print(f"Subtitles: {srt_file}  ({len(segs)} segments)")
        if not segs:
            print("  Nothing transcribed: is there speech in the selected language?")
            return None
        return srt_file, transcriber.name


class VideoSubtitles:
    """Gets the video, keeps the subtitles it came with, adds subtitles of its own (OCR or Whisper), converts the
    Chinese script if asked, then adds every track to the video."""

    def __init__(self, request: VideoRequest):
        self.request = request
        self.maker: SubtitleMaker = OcrSubtitles(request) if request.use_ocr else SpeechSubtitles(request)

    def run(self) -> Path:
        video_file = self._video()
        paths.srt.mkdir(parents=True, exist_ok=True)
        tracks = self._source_tracks(video_file)
        made = self.maker.make(video_file)
        if made is not None:
            tracks.append(made)
        self._convert_script()
        return self._mux(video_file, tracks)

    def _video(self) -> Path:
        request = self.request
        if request.video_path is not None:
            print(f"Using local video: {request.video_path}")
            return request.video_path
        return download_video(request.url, paths.videos, app_id=request.app_id, language=request.language)

    @staticmethod
    def _source_tracks(video_file: Path) -> list[Track]:
        """The subtitles the video came with, copied to output/srt: the files next to it (where yt-dlp writes the
        platform's captions, and where a local video may have its .srt files), else the tracks of its container."""
        found = source_subtitles(video_file, paths.temp)
        multiple = len(found) > 1
        tracks = []
        for i, (srt_file, tag) in enumerate(found):
            copy = paths.srt / f"{video_file.stem}_source{f'_{i}' if multiple else ''}.srt"
            shutil.copy(srt_file, copy)
            print(f"Existing subtitles found: {srt_file.name} -> {copy}")
            tracks.append((copy, f"Source ({tag})" if multiple else "Source"))
        return tracks

    def _convert_script(self) -> None:
        """Every SRT of output/srt (the source ones and the new ones) in the Chinese script asked for."""
        source_script = self.request.language.profile.script
        target = self.request.convert_target
        if target is not None and source_script is not None:
            print(f"\n=== Character conversion ({source_script} -> {target}) ===")
            convert_srt_dir(source_script, target)

    def _mux(self, video_file: Path, tracks: list[Track]) -> Path:
        print("\n=== Muxing subtitles into video ===")
        output_file = paths.final / f"{video_file.stem}.mp4"
        # Without any track, or when ffmpeg fails, the run fails (and the GUI says so).
        if not tracks:
            raise ConverterError("No subtitles to add to the video.")
        if not mux_subtitles(video_file, tracks, output_file, paths.temp,
                             subtitle_lang=self.request.language.profile.iso639_2):
            raise ConverterError("Could not add the subtitles to the video (see the ffmpeg error above).")
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
        return output_file


def run(request: VideoRequest) -> Path:
    return VideoSubtitles(request).run()
