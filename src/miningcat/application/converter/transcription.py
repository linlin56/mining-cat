from pathlib import Path

from miningcat.domain.languages import Language
from miningcat.domain.subtitles.punctuation import (
    fix_leading_punct,
    fix_trailing_opening_punct,
    prepare_text,
    restore_opening_punct,
)
from miningcat.domain.subtitles.segment import Segment


def _fix_punctuation(segs: list[Segment], lang: Language) -> list[Segment]:
    return fix_trailing_opening_punct(fix_leading_punct(segs, lang), lang)


def align_chapter(aligner, audio_file: Path, text_file: Path, lang: Language) -> tuple[list[Segment], int]:
    """The subtitles of a chapter: its text aligned on its audio (by speech_engines.load_aligner's model). Also
    returns the length of the text."""
    chapter_text = prepare_text(text_file.read_text(encoding="utf-8").strip(), lang)
    segs = _fix_punctuation(aligner.align(audio_file, chapter_text, lang), lang)
    return restore_opening_punct(segs, chapter_text, lang), len(chapter_text)


def transcribe(transcriber, audio_file: Path, lang: Language) -> list[Segment]:
    """The subtitles of an audio file transcribed by speech_engines.load_transcriber's model."""
    return _fix_punctuation(transcriber.transcribe(audio_file, lang), lang)
