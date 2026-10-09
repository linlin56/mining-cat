import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps import mp4_export as export
from miningcat.infrastructure.media import fonts, still_video
from miningcat.infrastructure.media.title_card import TitleCardRenderer

from shared import redirect_path


def test_run_exits_if_no_audio_dir(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "chapters_audio", tmp_path / "nonexistent")
    with pytest.raises(ConverterError):
        export.run()


def test_run_raises_if_audio_dir_empty(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    redirect_path(monkeypatch, "chapters_audio", audio_dir)
    redirect_path(monkeypatch, "final", tmp_path / "final")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    with pytest.raises(FileNotFoundError):
        export.run()


# --- _load_font / _fit_font ---

def test_load_font_returns_font():
    font = fonts.load_font(20)
    assert font is not None


def test_fit_font_returns_font():
    from PIL import ImageDraw
    img = Image.new("RGB", (200, 200))
    draw = ImageDraw.Draw(img)
    font = fonts.fit_font(draw, "Hello", 20, 180)
    assert font is not None


# --- _draw_text_overlay ---

def test_draw_text_overlay_with_titles():
    frame = Image.new("RGB", (200, 200), "black")
    result = TitleCardRenderer(200, 200).draw_titles(frame, "My Book", "Chapter 1")
    assert result is not None
    assert result.size == (200, 200)


def test_draw_text_overlay_no_titles():
    frame = Image.new("RGB", (100, 100), "black")
    result = TitleCardRenderer(100, 100).draw_titles(frame, None, None)
    assert result is frame


def test_draw_text_overlay_book_only():
    frame = Image.new("RGB", (200, 100), "black")
    result = TitleCardRenderer(200, 100).draw_titles(frame, "Only Title", None)
    assert result.size == (200, 100)


# --- _load_chapter_titles ---

def test_load_chapter_titles_no_file(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "temp", tmp_path)
    assert export.chapter_titles() == {}


def test_load_chapter_titles_with_file(tmp_path, monkeypatch):
    manifest = tmp_path / "ebook_chapters.json"
    manifest.write_text(json.dumps([
        {"index": 1, "title": "Intro"},
        {"index": 2, "title": "Ch 1"},
    ]), encoding="utf-8")
    redirect_path(monkeypatch, "temp", tmp_path)
    result = export.chapter_titles()
    assert result == {1: "Intro", 2: "Ch 1"}


def test_load_chapter_titles_invalid_json(tmp_path, monkeypatch):
    (tmp_path / "ebook_chapters.json").write_text("not json")
    redirect_path(monkeypatch, "temp", tmp_path)
    assert export.chapter_titles() == {}


def test_load_chapter_titles_skips_entries_without_index(tmp_path, monkeypatch):
    manifest = tmp_path / "ebook_chapters.json"
    manifest.write_text(json.dumps([{"title": "No index"}, {"index": 1, "title": "OK"}]))
    redirect_path(monkeypatch, "temp", tmp_path)
    result = export.chapter_titles()
    assert result == {1: "OK"}


# --- get_chapter_audio_files ---

def test_get_chapter_audio_files_returns_files(tmp_path, monkeypatch):
    (tmp_path / "ch1.mp3").touch()
    (tmp_path / "ch2.mp3").touch()
    redirect_path(monkeypatch, "chapters_audio", tmp_path)
    files = export.chapter_audio_files()
    assert len(files) == 2


# --- get_audio_duration ---

def test_get_audio_duration(tmp_path):
    audio_file = tmp_path / "ch.mp3"
    audio_file.touch()
    with patch("ffmpeg.probe", return_value={"format": {"duration": "123.456"}}):
        dur = still_video.audio_duration(audio_file)
    assert abs(dur - 123.456) < 0.001


# --- create_video_frame ---

def test_create_video_frame_no_cover(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "temp", tmp_path)
    with patch.object(export, "epub_cover", return_value=None):
        path = export.video_frame(width=100, height=100, book_title="Test", chapter_stem="ch001")
    assert path.exists()
    assert path.suffix == ".png"


def test_create_video_frame_cached(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "temp", tmp_path)
    cached = tmp_path / "video_frame_ch001.png"
    cached.write_bytes(b"fake")
    path = export.video_frame(chapter_stem="ch001")
    assert path == cached


def test_create_video_frame_with_cover(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "temp", tmp_path)
    cover = tmp_path / "cover.jpg"
    Image.new("RGB", (50, 80), "blue").save(cover)
    with patch.object(export, "epub_cover", return_value=cover):
        path = export.video_frame(width=100, height=100, chapter_stem="with_cover")
    assert path.exists()


# --- export_chapter_to_mp4 ---

def test_export_chapter_to_mp4_no_srt(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    result = export.export_chapter(
        tmp_path / "ch001.mp3",
        tmp_path / "frame.png",
        tmp_path / "out.mp4",
    )
    assert result is False


# --- run (chapter_num path) ---

def test_run_single_chapter_invalid_num(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "ch001.mp3").touch()
    redirect_path(monkeypatch, "chapters_audio", audio_dir)
    redirect_path(monkeypatch, "final", tmp_path / "final")
    redirect_path(monkeypatch, "temp", tmp_path)
    with patch.object(export, "epub_title", return_value=None):
        with pytest.raises(ConverterError):
            export.run(chapter_num=99)


def test_run_single_chapter_no_srt(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "ch001.mp3").touch()
    redirect_path(monkeypatch, "chapters_audio", audio_dir)
    redirect_path(monkeypatch, "final", tmp_path / "final")
    redirect_path(monkeypatch, "temp", tmp_path)
    frame = tmp_path / "frame.png"
    Image.new("RGB", (10, 10)).save(frame)

    with patch.object(export, "video_frame", return_value=frame), \
         patch.object(export, "export_chapter", return_value=False), \
         patch.object(export, "epub_title", return_value=None):
        export.run(chapter_num=1)


def test_run_all_chapters(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "ch001.mp3").touch()
    (audio_dir / "ch002.mp3").touch()
    redirect_path(monkeypatch, "chapters_audio", audio_dir)
    redirect_path(monkeypatch, "final", tmp_path / "final")
    redirect_path(monkeypatch, "temp", tmp_path)
    frame = tmp_path / "frame.png"
    Image.new("RGB", (10, 10)).save(frame)

    with patch.object(export, "video_frame", return_value=frame), \
         patch.object(export, "export_chapter", return_value=False), \
         patch.object(export, "epub_title", return_value=None):
        export.run(all_chapters=True)
