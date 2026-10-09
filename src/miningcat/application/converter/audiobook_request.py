from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.modes import ConversionMode
from miningcat.application.converter.source_files import load_chapters, normalize_ebook_selection
from miningcat.domain.languages import Language


@dataclass(frozen=True)
class AudiobookRequest:
    """An audiobook or ebook conversion: its mode, language, files and options."""

    mode: ConversionMode
    language: Language
    model_name: str = "base"
    # Chinese script the subtitles are converted to.
    convert_target: str | None = None
    # edge-tts voice reading the book (Generate audio mode).
    voice_id: str | None = None
    audio_files: list[Path] = field(default_factory=list)
    ebook_files: list[Path] = field(default_factory=list)
    # Indices of the chapters to convert, and the book's number of chapters.
    selected_chapters: list[int] = field(default_factory=list)
    total_chapters: int = 0

    @property
    def chapter_numbers(self) -> str | None:
        """The --chapters option of the ebook extraction ("1,3,4"), None when every chapter is converted."""
        if self.selected_chapters and len(self.selected_chapters) < self.total_chapters:
            return ",".join(str(i + 1) for i in self.selected_chapters)
        return None


class AudiobookRequestBuilder:
    """Builds an AudiobookRequest from the user's choices, checking that the mode gets what it needs:

        AudiobookRequestBuilder(ConversionMode.STANDARD, Language.FRENCH)
            .audio(files).ebook(files, chapters=[0, 2]).whisper("small").build()
    """

    def __init__(self, mode: ConversionMode, language: Language):
        self._mode = mode
        self._values: dict = {"mode": mode, "language": language}

    def whisper(self, model_name: str) -> Self:
        self._values["model_name"] = model_name
        return self

    def convert_to(self, script: str | None) -> Self:
        self._values["convert_target"] = script
        return self

    def audio(self, files: list[Path]) -> Self:
        if self._mode.needs_audio:
            if not files:
                raise ConverterError("Add at least one audio file (MP3 or M4B).", "Missing files")
            self._values["audio_files"] = list(files)
        return self

    def ebook(self, files: list[Path], chapters: list | None = None) -> Self:
        """The book, and the indices of the chapters to convert (unreadable indices are ignored)."""
        if not self._mode.needs_ebook:
            return self
        files = normalize_ebook_selection(files)
        if not files:
            raise ConverterError("Select an EPUB or TXT file.", "Missing file")
        try:
            book_chapters = load_chapters(files)
        except Exception:
            book_chapters = []
        selected = sorted({i for i in chapters or [] if isinstance(i, int) and 0 <= i < len(book_chapters)})
        if book_chapters and not selected:
            raise ConverterError("Select at least one chapter.", "No chapters selected")
        self._values.update(ebook_files=files, selected_chapters=selected, total_chapters=len(book_chapters))
        return self

    def voice(self, label: str | None) -> Self:
        """The edge-tts voice reading the book, by its label (Generate audio mode)."""
        if self._mode is ConversionMode.GENERATE_AUDIO:
            voice_id = self._values["language"].profile.voice_id(label) if label else None
            if voice_id is None:
                raise ConverterError("Pick a voice.", "Missing voice")
            self._values["voice_id"] = voice_id
        return self

    def build(self) -> AudiobookRequest:
        if self._mode.needs_audio and not self._values.get("audio_files"):
            raise ConverterError("Add at least one audio file (MP3 or M4B).", "Missing files")
        if self._mode.needs_ebook and not self._values.get("ebook_files"):
            raise ConverterError("Select an EPUB or TXT file.", "Missing file")
        if self._mode is ConversionMode.GENERATE_AUDIO and not self._values.get("voice_id"):
            raise ConverterError("Pick a voice.", "Missing voice")
        return AudiobookRequest(**self._values)
