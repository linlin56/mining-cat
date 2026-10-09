from unittest.mock import MagicMock, patch

import pytest

from miningcat.application.converter import transcription
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps.subtitles import Alignment, Transcription
from miningcat.config.paths import paths
from miningcat.domain.languages import Language
from miningcat.infrastructure.speech.whisper import Whisper


def test_run_exits_if_no_audio_dir(tmp_path, monkeypatch):
    with pytest.raises(ConverterError):
        Alignment().run()


def test_run_exits_if_no_text_dir(tmp_path, monkeypatch):
    audio_dir = paths.chapters_audio
    audio_dir.mkdir(parents=True)
    with pytest.raises(ConverterError):
        Alignment().run()


def test_run_only_ch_sets_from_ch(tmp_path, monkeypatch):
    with pytest.raises(ConverterError):
        Alignment(only_ch=2).run()



# --- align_chapter / transcribe ---

def test_align_chapter(tmp_path):
    text_file = tmp_path / "chapter.txt"
    text_file.write_text("Hello world", encoding="utf-8")
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    mock_model = MagicMock()
    mock_model.align.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}

    segs, text_len = transcription.align_chapter(Whisper(mock_model), audio_file, text_file, Language.ENGLISH_US)
    assert text_len == len("Hello world")
    assert len(segs) == 1
    assert segs[0].text == "Hello world"


def test_transcribe_chapter(tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": [{"start": 0.0, "end": 2.0, "text": "Test"}]}

    segs = transcription.transcribe(Whisper(mock_model), audio_file, Language.ENGLISH_US)
    assert len(segs) == 1
    assert segs[0].text == "Test"


# --- run_transcribe ---

def test_run_transcribe_exits_if_no_audio_dir(tmp_path, monkeypatch):
    with pytest.raises(ConverterError):
        Transcription().run()


def test_run_transcribe_with_only_ch(tmp_path, monkeypatch):
    with pytest.raises(ConverterError):
        Transcription(only_ch=1).run()


def test_run_transcribe_processes_chapter(tmp_path, monkeypatch):
    audio_dir = paths.chapters_audio
    audio_dir.mkdir(parents=True)
    srt_dir = paths.srt
    (audio_dir / "chapter_001.mp3").touch()


    mock_model = MagicMock()
    mock_model.num_languages = 100
    mock_model.transcribe.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}]}

    with patch("stable_whisper.load_model", return_value=mock_model):
        Transcription(model_name="tiny", only_ch=1).run()

    assert (srt_dir / "chapter_001.srt").exists()


def test_run_transcribe_skips_existing(tmp_path, monkeypatch):
    audio_dir = paths.chapters_audio
    audio_dir.mkdir(parents=True)
    srt_dir = paths.srt
    srt_dir.mkdir(parents=True)
    (audio_dir / "chapter_001.mp3").touch()
    (srt_dir / "chapter_001.srt").write_text("existing")


    mock_model = MagicMock()
    mock_model.num_languages = 100
    with patch("stable_whisper.load_model", return_value=mock_model):
        Transcription(model_name="tiny").run()

    mock_model.transcribe.assert_not_called()


# --- run (full alignment) ---

def test_run_processes_chapter(tmp_path, monkeypatch):
    audio_dir = paths.chapters_audio
    text_dir = paths.chapters_text
    srt_dir = paths.srt
    audio_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    (audio_dir / "chapter_001.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("Hello world", encoding="utf-8")


    mock_model = MagicMock()
    mock_model.num_languages = 100
    mock_model.align.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}

    with patch("stable_whisper.load_model", return_value=mock_model):
        Alignment(model_name="tiny", only_ch=1).run()

    assert (srt_dir / "chapter_001.srt").exists()


def test_run_skips_existing_srt(tmp_path, monkeypatch):
    audio_dir = paths.chapters_audio
    text_dir = paths.chapters_text
    srt_dir = paths.srt
    audio_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    srt_dir.mkdir(parents=True)
    (audio_dir / "chapter_001.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("Hello", encoding="utf-8")
    (srt_dir / "chapter_001.srt").write_text("existing")


    mock_model = MagicMock()
    mock_model.num_languages = 100
    with patch("stable_whisper.load_model", return_value=mock_model):
        Alignment(model_name="tiny").run()

    mock_model.align.assert_not_called()


def test_run_warns_on_count_mismatch(tmp_path, monkeypatch, capsys):
    audio_dir = paths.chapters_audio
    text_dir = paths.chapters_text
    srt_dir = paths.srt
    audio_dir.mkdir(parents=True)
    text_dir.mkdir(parents=True)
    (audio_dir / "chapter_001.mp3").touch()
    (audio_dir / "chapter_002.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("A", encoding="utf-8")


    mock_model = MagicMock()
    mock_model.num_languages = 100
    mock_model.align.return_value = {"segments": []}
    with patch("stable_whisper.load_model", return_value=mock_model):
        Alignment(model_name="tiny").run()

    out = capsys.readouterr().out
    assert "Warning" in out
