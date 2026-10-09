from pathlib import Path

from miningcat.domain.audiobook.chapter import Chapter, format_timestamp
from miningcat.domain.audiobook.source_mode import AudioSourceMode

# --- Chapter dataclass ---

def test_chapter_duration():
    ch = Chapter(1, "Intro", 10.0, 70.0)
    assert ch.duration == 60.0


def test_chapter_start_str():
    ch = Chapter(1, "Intro", 3661.5, 7200.0)
    assert ch.start_str == "01:01:01.500"


def test_chapter_end_str():
    ch = Chapter(1, "Intro", 0.0, 7200.0)
    assert ch.end_str == "02:00:00.000"


def test_chapter_slug_sanitizes_special_chars():
    ch = Chapter(3, "A/B:C", 0.0, 1.0)
    assert ch.slug == "003_A_B_C"


def test_chapter_slug_replaces_spaces():
    ch = Chapter(1, "My Chapter", 0.0, 1.0)
    assert ch.slug == "001_My_Chapter"


# --- format_timestamp ---

def test_seconds_to_hhmmss_zero():
    assert format_timestamp(0) == "00:00:00.000"


def test_seconds_to_hhmmss_complex():
    assert format_timestamp(3661.5) == "01:01:01.500"


# --- AudioSourceMode ---

def test_one_file_is_one_chapter():
    assert AudioSourceMode.of([Path("audio.mp3")]) is AudioSourceMode.SINGLE_AUDIO
    assert AudioSourceMode.of([Path("audio.ogg")]) is AudioSourceMode.SINGLE_AUDIO


def test_several_files_are_one_chapter_each():
    assert AudioSourceMode.of([Path("ch1.mp3"), Path("ch2.flac")]) is AudioSourceMode.MULTI_AUDIO


def test_an_m4b_file_is_split_by_its_chapters():
    assert AudioSourceMode.of([Path("book.M4B")]) is AudioSourceMode.SINGLE_M4B
