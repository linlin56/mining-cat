"""The converter's jobs as the GUIs run them: each step in its own process, its output in the job's log."""
from abc import ABC, abstractmethod
from pathlib import Path

from miningcat.application.converter.audiobook_request import AudiobookRequest
from miningcat.application.converter.cli_command import CliCommand
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.modes import Step
from miningcat.application.converter.progress import ProgressListener
from miningcat.application.converter.source_files import copy_sources
from miningcat.application.converter.steps.script_conversion import convert_srt_dir
from miningcat.application.converter.video_request import VideoRequest
from miningcat.config.paths import paths
from miningcat.infrastructure.system import processes


class Job(ABC):
    """A conversion run by a GUI."""

    kind: str

    @abstractmethod
    def run(self, listener: ProgressListener):
        """Runs the job to its end, reporting to the listener. Raises when a step fails."""

    @staticmethod
    def _run_command(command: list[str], name: str, listener: ProgressListener) -> None:
        returncode = processes.run(command, listener.log)
        if returncode != 0:
            raise ConverterError(f"Command '{name}' failed (code {returncode})")


def run_job(job: Job, listener: ProgressListener) -> tuple[bool, object]:
    """Runs a job, its failure written in the log. Returns whether it succeeded, and what it returned."""
    try:
        return True, job.run(listener)
    except Exception as exc:
        listener.log(f"\n[ERROR] {exc}\n")
        listener.status("Error - check the log.", 0)
        return False, None


class AudiobookJob(Job):
    """An audiobook or ebook conversion: the steps of its mode, then the character conversion if asked."""

    kind = "audiobook"

    def __init__(self, request: AudiobookRequest):
        self.request = request

    def command(self, step: Step) -> list[str]:
        request = self.request
        command = CliCommand(step.command)
        if step.command == "epub":
            command.option("--chapters", request.chapter_numbers)
        elif step.command in ("align", "transcribe"):
            command.option("--language", request.language.id).option("--model", request.model_name)
        elif step.command == "export":
            command.flag("--all").option("--language", request.language.id)
        elif step.command == "tts":
            command.option("--voice", request.voice_id).option("--language", request.language.id)
        return command.build()

    def run(self, listener: ProgressListener) -> None:
        request = self.request
        copy_sources(request.audio_files if request.mode.needs_audio else [],
                     request.ebook_files if request.mode.needs_ebook else [], listener.log)
        for step in request.mode.steps:
            listener.status(step.label + "…", step.pct)
            listener.log(f"\n{step.label}\n")
            self._run_command(self.command(step), step.command, listener)
            if step.command in ("align", "transcribe", "tts") and request.convert_target is not None:
                listener.status("Step 3.5 - Character conversion…", 45)
                listener.log("\nStep 3.5 - Character conversion\n")
                convert_srt_dir(request.language.profile.script, request.convert_target)
                listener.log("  Done.\n")
        listener.status("Done", 100)
        listener.log("\nPipeline complete.\n")


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def find_video_srt(directory: Path) -> Path | None:
    """The subtitles of the last video, for its frequency lists: the Whisper or OCR ones (always made, most
    complete) rather than the ones the platform gave."""
    return (_latest_file(directory, "*_whisper.srt")
            or _latest_file(directory, "*_ocr.srt")
            or _latest_file(directory, "*.srt"))


class VideoJob(Job):
    """A video conversion (python -m miningcat video). Returns the video's subtitles."""

    kind = "video"

    def __init__(self, request: VideoRequest):
        self.request = request

    def command(self) -> list[str]:
        request = self.request
        command = (CliCommand("video").option("--model", request.model_name).option("--language", request.language.id)
                   .option("--file", request.video_path).option("--url", request.url)
                   .option("--convert-to", request.convert_target).option("--audio-track", request.audio_track))
        if request.use_ocr:
            command.flag("--ocr").option("--ocr-fps", request.ocr_fps)
            if request.ocr_region is not None:
                command.option("--ocr-region", ",".join(str(v) for v in request.ocr_region))
        return command.build()

    def run(self, listener: ProgressListener) -> Path | None:
        if self.request.video_path is not None:
            listener.status("Transcribing local video…", 10)
            listener.log("\nStep 1/1 - Local video subtitles\n")
        else:
            listener.status("Downloading & transcribing video…", 10)
            listener.log("\nStep 1/1 - Video download + subtitles\n")
        self._run_command(self.command(), "video", listener)
        listener.status("Done", 100)
        listener.log("\nPipeline complete.\n")
        return find_video_srt(paths.srt)
