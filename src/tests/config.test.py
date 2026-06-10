import pytest
import config


def test_detect_audio_mode_single_mp3(tmp_path, monkeypatch):
    (tmp_path / "audio.mp3").touch()
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    mode, files = config.detect_audio_mode()
    assert mode == "single_mp3"
    assert len(files) == 1


def test_detect_audio_mode_multi_mp3(tmp_path, monkeypatch):
    (tmp_path / "ch1.mp3").touch()
    (tmp_path / "ch2.mp3").touch()
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    mode, files = config.detect_audio_mode()
    assert mode == "multi_mp3"
    assert len(files) == 2


def test_detect_audio_mode_single_m4b(tmp_path, monkeypatch):
    (tmp_path / "book.m4b").touch()
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    mode, files = config.detect_audio_mode()
    assert mode == "single_m4b"
    assert len(files) == 1


def test_detect_audio_mode_no_files_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_AUDIOBOOK", tmp_path)
    with pytest.raises(FileNotFoundError):
        config.detect_audio_mode()
