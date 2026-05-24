import pytest
import export


def test_run_exits_if_no_audio_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    with pytest.raises(SystemExit):
        export.run()


def test_run_raises_if_audio_dir_empty(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(export, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(export, "DIR_FINAL", tmp_path / "final")
    monkeypatch.setattr(export, "DIR_TEMP", tmp_path / "temp")
    with pytest.raises(FileNotFoundError):
        export.run()
