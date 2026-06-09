import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import audio
import config
from audio import Chapter


def test_run_dry_run_multi_mp3(tmp_path, monkeypatch):
    (tmp_path / "ch1.mp3").touch()
    (tmp_path / "ch2.mp3").touch()
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    audio.run(dry_run=True)


def test_run_dry_run_single_mp3(tmp_path, monkeypatch):
    (tmp_path / "audio.mp3").touch()
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    audio.run(dry_run=True)


def test_run_no_audio_files_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    with pytest.raises(SystemExit):
        audio.run()


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


# --- _seconds_to_hhmmss ---

def test_seconds_to_hhmmss_zero():
    assert audio._seconds_to_hhmmss(0) == "00:00:00.000"


def test_seconds_to_hhmmss_complex():
    assert audio._seconds_to_hhmmss(3661.5) == "01:01:01.500"


# --- get_audiobook_file ---

def test_get_audiobook_file_raises_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "DIR_AUDIOBOOK", tmp_path)
    with pytest.raises(FileNotFoundError):
        audio.get_audiobook_file()


def test_get_audiobook_file_returns_first(tmp_path, monkeypatch):
    (tmp_path / "book.m4b").touch()
    monkeypatch.setattr(audio, "DIR_AUDIOBOOK", tmp_path)
    result = audio.get_audiobook_file()
    assert result.name == "book.m4b"


def test_get_audiobook_file_warns_on_multiple(tmp_path, monkeypatch, capsys):
    (tmp_path / "a.m4b").touch()
    (tmp_path / "b.m4b").touch()
    monkeypatch.setattr(audio, "DIR_AUDIOBOOK", tmp_path)
    audio.get_audiobook_file()
    assert "Warning" in capsys.readouterr().out


# --- probe_chapters ---

def test_probe_chapters_parses_output(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    fake_data = {"chapters": [
        {"tags": {"title": "Intro"}, "start_time": "0.0", "end_time": "60.0"},
        {"tags": {"title": "Ch 1"}, "start_time": "60.0", "end_time": "180.0"},
    ]}
    mock_result = MagicMock(returncode=0, stdout=json.dumps(fake_data))
    with patch("subprocess.run", return_value=mock_result):
        chapters = audio.probe_chapters(m4b)
    assert len(chapters) == 2
    assert chapters[0].title == "Intro"
    assert chapters[1].end_time == 180.0


def test_probe_chapters_ffprobe_failure(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    mock_result = MagicMock(returncode=1, stderr="Error!")
    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError):
            audio.probe_chapters(m4b)


def test_probe_chapters_no_chapters(tmp_path, capsys):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    mock_result = MagicMock(returncode=0, stdout='{"chapters": []}')
    with patch("subprocess.run", return_value=mock_result):
        chapters = audio.probe_chapters(m4b)
    assert chapters == []


def test_probe_chapters_default_title(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    fake_data = {"chapters": [{"tags": {}, "start_time": "0.0", "end_time": "30.0"}]}
    mock_result = MagicMock(returncode=0, stdout=json.dumps(fake_data))
    with patch("subprocess.run", return_value=mock_result):
        chapters = audio.probe_chapters(m4b)
    assert chapters[0].title == "Chapter 1"


# --- print_chapters ---

def test_print_chapters(capsys):
    chapters = [Chapter(1, "Intro", 0.0, 60.0), Chapter(2, "Ch 1", 60.0, 120.0)]
    audio.print_chapters(chapters, Path("book.m4b"))
    out = capsys.readouterr().out
    assert "Intro" in out
    assert "book.m4b" in out


# --- save_chapters_json ---

def test_save_chapters_json(tmp_path):
    chapters = [Chapter(1, "Intro", 0.0, 60.0), Chapter(2, "Ch 1", 60.0, 120.0)]
    path = audio.save_chapters_json(chapters, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["title"] == "Intro"
    assert data[1]["slug"] == chapters[1].slug


# --- extract_chapter (skip path) ---

def test_extract_chapter_skips_if_exists(tmp_path):
    chapter = Chapter(1, "Intro", 0.0, 60.0)
    out_path = tmp_path / f"{chapter.slug}.mp3"
    out_path.write_bytes(b"existing")
    result = audio.extract_chapter(tmp_path / "book.m4b", chapter, tmp_path)
    assert result == out_path


# --- copy_mp3_chapters ---

def test_copy_mp3_chapters_copies_files(tmp_path):
    src = tmp_path / "src" / "ch1.mp3"
    src.parent.mkdir()
    src.write_bytes(b"audio")
    dst_dir = tmp_path / "dst"
    result = audio.copy_mp3_chapters([src], dst_dir)
    assert len(result) == 1
    assert (dst_dir / "ch1.mp3").read_bytes() == b"audio"


def test_copy_mp3_chapters_skips_existing(tmp_path):
    src = tmp_path / "src" / "ch1.mp3"
    src.parent.mkdir()
    src.write_bytes(b"new")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "ch1.mp3").write_bytes(b"old")
    audio.copy_mp3_chapters([src], dst_dir)
    assert (dst_dir / "ch1.mp3").read_bytes() == b"old"


# --- run non-dry-run paths ---

def test_run_multi_mp3_copies_files(tmp_path, monkeypatch):
    (tmp_path / "ch1.mp3").write_bytes(b"a1")
    (tmp_path / "ch2.mp3").write_bytes(b"a2")
    dst = tmp_path / "chapters"
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    monkeypatch.setattr(audio, "DIR_CHAPTERS_AUDIO", dst)
    audio.run(dry_run=False)
    assert (dst / "ch1.mp3").exists()
    assert (dst / "ch2.mp3").exists()


def test_run_single_mp3_copies_file(tmp_path, monkeypatch):
    (tmp_path / "audio.mp3").write_bytes(b"data")
    dst = tmp_path / "chapters"
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    monkeypatch.setattr(audio, "DIR_CHAPTERS_AUDIO", dst)
    audio.run(dry_run=False)
    assert (dst / "audio.mp3").exists()
