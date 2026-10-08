import json
from pathlib import Path

import pytest

from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps import audio_preparation
from miningcat.config.paths import paths
from miningcat.domain.audiobook.chapter import Chapter
from miningcat.domain.audiobook.source_mode import AudioSourceMode


def audiobook(*names: str) -> None:
    paths.audiobook.mkdir(parents=True, exist_ok=True)
    for name in names:
        (paths.audiobook / name).write_bytes(b"audio")


def test_run_dry_run_multi_mp3():
    audiobook("ch1.mp3", "ch2.mp3")
    audio_preparation.run(dry_run=True)
    assert not paths.chapters_audio.exists()


def test_run_dry_run_single_mp3():
    audiobook("audio.mp3")
    audio_preparation.run(dry_run=True)


def test_run_without_audio_files_fails():
    with pytest.raises(ConverterError):
        audio_preparation.run()


def test_detect_audio_mode():
    audiobook("ch1.mp3", "ch2.flac", "notes.txt")
    mode, files = audio_preparation.detect_audio_mode()
    assert mode is AudioSourceMode.MULTI_AUDIO
    assert [f.name for f in files] == ["ch1.mp3", "ch2.flac"]


# --- print_chapters ---

def test_print_chapters(capsys):
    chapters = [Chapter(1, "Intro", 0.0, 60.0), Chapter(2, "Ch 1", 60.0, 120.0)]
    audio_preparation.print_chapters(chapters, Path("book.m4b"))
    out = capsys.readouterr().out
    assert "Intro" in out
    assert "book.m4b" in out


# --- save_chapters_json ---

def test_save_chapters_json(tmp_path):
    chapters = [Chapter(1, "Intro", 0.0, 60.0), Chapter(2, "Ch 1", 60.0, 120.0)]
    path = audio_preparation.save_chapters_json(chapters, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["title"] == "Intro"
    assert data[1]["slug"] == chapters[1].slug


# --- copy_audio_chapters ---

def test_copy_audio_chapters_copies_files(tmp_path):
    src = tmp_path / "src" / "ch1.mp3"
    src.parent.mkdir()
    src.write_bytes(b"audio")
    dst_dir = tmp_path / "dst"
    result = audio_preparation.copy_audio_chapters([src], dst_dir)
    assert len(result) == 1
    assert (dst_dir / "ch1.mp3").read_bytes() == b"audio"


def test_copy_audio_chapters_skips_existing(tmp_path):
    src = tmp_path / "src" / "ch1.mp3"
    src.parent.mkdir()
    src.write_bytes(b"new")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "ch1.mp3").write_bytes(b"old")
    audio_preparation.copy_audio_chapters([src], dst_dir)
    assert (dst_dir / "ch1.mp3").read_bytes() == b"old"


def test_copy_audio_chapters_handles_non_mp3(tmp_path):
    src = tmp_path / "src" / "ch1.flac"
    src.parent.mkdir()
    src.write_bytes(b"audio")
    dst_dir = tmp_path / "dst"
    result = audio_preparation.copy_audio_chapters([src], dst_dir)
    assert (dst_dir / "ch1.flac").read_bytes() == b"audio"


# --- run non-dry-run paths ---

def test_run_multi_mp3_copies_files():
    audiobook("ch1.mp3", "ch2.mp3")
    audio_preparation.run(dry_run=False)
    assert (paths.chapters_audio / "ch1.mp3").exists()
    assert (paths.chapters_audio / "ch2.mp3").exists()


def test_run_single_mp3_copies_file():
    audiobook("audio.mp3")
    audio_preparation.run(dry_run=False)
    assert (paths.chapters_audio / "audio.mp3").exists()


def test_run_splits_an_m4b_by_its_chapters(monkeypatch):
    audiobook("book.m4b")
    chapters = [Chapter(1, "Intro", 0.0, 60.0)]
    monkeypatch.setattr(audio_preparation, "probe_chapters", lambda path: chapters)
    extracted = []
    monkeypatch.setattr(audio_preparation, "extract_chapter",
                        lambda path, chapter, folder: extracted.append(chapter) or folder / f"{chapter.slug}.mp3")
    audio_preparation.run()
    assert extracted == chapters
    assert (paths.temp / "chapters.json").exists()


def test_run_fails_on_an_m4b_without_chapters(monkeypatch):
    audiobook("book.m4b")
    monkeypatch.setattr(audio_preparation, "probe_chapters", lambda path: [])
    with pytest.raises(ConverterError):
        audio_preparation.run()
