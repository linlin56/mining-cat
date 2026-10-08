import json
from unittest.mock import MagicMock, patch

import pytest

from miningcat.domain.audiobook.chapter import Chapter
from miningcat.infrastructure.media import m4b as m4b_files

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
        chapters = m4b_files.probe_chapters(m4b)
    assert len(chapters) == 2
    assert chapters[0].title == "Intro"
    assert chapters[1].end_time == 180.0


def test_probe_chapters_ffprobe_failure(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    mock_result = MagicMock(returncode=1, stderr="Error!")
    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError):
            m4b_files.probe_chapters(m4b)


def test_probe_chapters_no_chapters(tmp_path, capsys):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    mock_result = MagicMock(returncode=0, stdout='{"chapters": []}')
    with patch("subprocess.run", return_value=mock_result):
        chapters = m4b_files.probe_chapters(m4b)
    assert chapters == []


def test_probe_chapters_default_title(tmp_path):
    m4b = tmp_path / "book.m4b"
    m4b.touch()
    fake_data = {"chapters": [{"tags": {}, "start_time": "0.0", "end_time": "30.0"}]}
    mock_result = MagicMock(returncode=0, stdout=json.dumps(fake_data))
    with patch("subprocess.run", return_value=mock_result):
        chapters = m4b_files.probe_chapters(m4b)
    assert chapters[0].title == "Chapter 1"


# --- extract_chapter (skip path) ---

def test_extract_chapter_skips_if_exists(tmp_path):
    chapter = Chapter(1, "Intro", 0.0, 60.0)
    out_path = tmp_path / f"{chapter.slug}.mp3"
    out_path.write_bytes(b"existing")
    result = m4b_files.extract_chapter(tmp_path / "book.m4b", chapter, tmp_path)
    assert result == out_path
