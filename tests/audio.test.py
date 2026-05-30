import pytest
import audio
import config


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
