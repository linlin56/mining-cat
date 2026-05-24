import pytest
import align


def test_run_exits_if_no_audio_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", tmp_path / "text")
    with pytest.raises(SystemExit):
        align.run()


def test_run_exits_if_no_text_dir(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", tmp_path / "nonexistent")
    with pytest.raises(SystemExit):
        align.run()
