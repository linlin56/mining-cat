from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Step:
    """A step of a conversion: its label in the GUI, its progress when it starts, its CLI command."""

    label: str
    pct: float
    command: str


class ConversionMode(Enum):
    """The three ways of making a mineable audiobook, and their steps."""

    STANDARD = "Standard"                          # the book's text aligned on its audio
    GENERATE_SUBTITLES = "Generate subtitles"      # no book: Whisper transcribes the audio
    GENERATE_AUDIO = "Generate audio"              # no audio: edge-tts reads the book

    @property
    def needs_audio(self) -> bool:
        return self is not ConversionMode.GENERATE_AUDIO

    @property
    def needs_ebook(self) -> bool:
        return self is not ConversionMode.GENERATE_SUBTITLES

    @property
    def steps(self) -> list[Step]:
        return _STEPS[self]

    @classmethod
    def labels(cls) -> list[str]:
        return [mode.value for mode in cls]


_STEPS = {
    ConversionMode.STANDARD: [
        Step("Step 1/4 - Audio preparation", 10, "audio"),
        Step("Step 2/4 - EPUB extraction", 25, "epub"),
        Step("Step 3/4 - Alignment", 40, "align"),
        Step("Step 4/4 - MP4 export", 80, "export"),
    ],
    ConversionMode.GENERATE_SUBTITLES: [
        Step("Step 1/3 - Audio preparation", 10, "audio"),
        Step("Step 2/3 - Transcription", 40, "transcribe"),
        Step("Step 3/3 - MP4 export", 80, "export"),
    ],
    ConversionMode.GENERATE_AUDIO: [
        Step("Step 1/3 - EPUB extraction", 10, "epub"),
        Step("Step 2/3 - Audio + subtitles", 40, "tts"),
        Step("Step 3/3 - MP4 export", 80, "export"),
    ],
}
