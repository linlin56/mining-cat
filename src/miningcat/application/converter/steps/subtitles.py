"""Step 3 of an audiobook: the subtitles of each chapter, aligned on its book (or transcribed without one)."""
import time
from abc import ABC, abstractmethod
from pathlib import Path

from tqdm import tqdm

from miningcat.application.converter import transcription
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps.script_conversion import normalize_whisper_script
from miningcat.config.paths import paths
from miningcat.domain.languages import Language
from miningcat.infrastructure.files.srt_files import save_srt
from miningcat.infrastructure.media.audio_files import glob_audio_files
from miningcat.infrastructure.speech.whisper import Whisper


class ChapterSubtitles(ABC):
    """Writes output/srt/<chapter>.srt for each chapter of output/chapters_audio, with a Whisper model.

    Chapters already done are skipped, unless the run starts `from_ch` (a retry); `only_ch` does one chapter.
    Subclasses say what the chapters are and how their subtitles are made."""

    def __init__(self, model_name: str = "tiny", language: Language = Language.MANDARIN_TW,
                 from_ch: int | None = None, only_ch: int | None = None):
        self.model_name = model_name
        self.language = language
        self.only_ch = only_ch
        self.from_ch = only_ch if only_ch is not None else from_ch
        self.whisper: Whisper | None = None

    @abstractmethod
    def _chapters(self) -> list[tuple]:
        """The chapters, as tuples starting with their audio file."""

    @abstractmethod
    def _subtitle(self, chapter: tuple, srt_path: Path) -> tuple[int, str]:
        """Writes the subtitles of a chapter. Returns their number of segments, and more to log about them."""

    def _require(self, folder: Path, hint: str) -> None:
        if not folder.exists():
            raise ConverterError(f"{folder} not found - {hint}")

    def run(self) -> None:
        chapters = self._chapters()
        paths.srt.mkdir(parents=True, exist_ok=True)
        start_idx = (self.from_ch - 1) if self.from_ch else 0
        chapters = chapters[start_idx:]
        print()

        print(f"Loading stable-whisper model '{self.model_name}'...")
        self.whisper = Whisper.load(self.model_name)
        self.whisper.ensure_supports(self.language)
        print()

        for i, chapter in enumerate(tqdm(chapters, desc="Chapters"), start=start_idx):
            ch_num = i + 1
            srt_path = paths.srt / (chapter[0].stem + ".srt")
            if srt_path.exists() and self.from_ch is None:
                tqdm.write(f"  Ch.{ch_num:03d} skip")
                continue
            t0 = time.time()
            segments, details = self._subtitle(chapter, srt_path)
            tqdm.write(f"  Ch.{ch_num:03d}  {segments} seg  {time.time() - t0:.0f}s" + (f"  {details}" if details else ""))
            if self.only_ch is not None:
                break

        print("\nDone.")


class Alignment(ChapterSubtitles):
    """Forced alignment of each chapter's text (output/chapters_text) on its audio."""

    def _chapters(self) -> list[tuple[Path, Path]]:
        self._require(paths.chapters_audio, "Run 'audio' first")
        self._require(paths.chapters_text, "Run 'epub' first")
        audio_files = glob_audio_files(paths.chapters_audio)
        text_files = sorted(paths.chapters_text.glob("chapter_*.txt"))
        print(f"Audio chapters: {len(audio_files)}")
        print(f"Text chapters:  {len(text_files)}")
        # If the counts don't match, the extra chapters are left out.
        if len(audio_files) != len(text_files):
            print(f"Warning: {len(audio_files)} audio vs {len(text_files)} text - "
                  f"processing min({len(audio_files)}, {len(text_files)}).")
        return list(zip(audio_files, text_files))

    def _subtitle(self, chapter: tuple[Path, Path], srt_path: Path) -> tuple[int, str]:
        audio_file, text_file = chapter
        segs, text_len = transcription.align_chapter(self.whisper, audio_file, text_file, self.language)
        save_srt(segs, srt_path)
        return len(segs), f"ebook={text_len:,}c"


class Transcription(ChapterSubtitles):
    """Whisper's transcription of each chapter, without a book: less accurate, but needs only the audio."""

    def _chapters(self) -> list[tuple[Path]]:
        self._require(paths.chapters_audio, "Run 'audio' first")
        audio_files = glob_audio_files(paths.chapters_audio)
        print(f"Audio chapters: {len(audio_files)}")
        return [(audio_file,) for audio_file in audio_files]

    def _subtitle(self, chapter: tuple[Path], srt_path: Path) -> tuple[int, str]:
        segs = transcription.transcribe(self.whisper, chapter[0], self.language)
        save_srt(segs, srt_path)
        normalize_whisper_script(srt_path, self.language)
        return len(segs), ""
