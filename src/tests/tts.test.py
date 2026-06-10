import asyncio
import pytest
from unittest.mock import patch, MagicMock
import tts


def test_run_exits_if_no_text_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "DIR_CHAPTERS_TEXT", tmp_path / "nonexistent")
    with pytest.raises(SystemExit):
        tts.run(voice="TestVoice")


def test_run_exits_if_no_text_files(tmp_path, monkeypatch):
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    monkeypatch.setattr(tts, "DIR_CHAPTERS_TEXT", text_dir)
    with pytest.raises(SystemExit):
        tts.run(voice="TestVoice")


def test_run_skips_existing_files(tmp_path, monkeypatch):
    text_dir = tmp_path / "text"
    audio_dir = tmp_path / "audio"
    srt_dir = tmp_path / "srt"
    text_dir.mkdir()
    audio_dir.mkdir()
    srt_dir.mkdir()
    (text_dir / "chapter_001.txt").write_text("Hello", encoding="utf-8")
    (audio_dir / "chapter_001.mp3").touch()
    (srt_dir / "chapter_001.srt").touch()

    monkeypatch.setattr(tts, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(tts, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(tts, "DIR_SRT", srt_dir)

    with patch("edge_tts.Communicate") as mock_comm_cls:
        tts.run(voice="TestVoice")
    mock_comm_cls.assert_not_called()


def test_synthesize_creates_files(tmp_path):
    async def _run():
        async def fake_stream():
            yield {"type": "audio", "data": b"audio_data"}
            yield {"type": "SentenceBoundary", "offset": 0, "duration": 10_000_000, "text": "Hello world."}

        mock_comm = MagicMock()
        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            n = await tts._synthesize(
                "Hello world.", "TestVoice",
                tmp_path / "out.mp3", tmp_path / "out.srt",
            )
        return n

    n = asyncio.run(_run())
    assert n == 1
    assert (tmp_path / "out.mp3").read_bytes() == b"audio_data"
    assert (tmp_path / "out.srt").exists()


def test_synthesize_clips_overlap(tmp_path):
    async def _run():
        async def fake_stream():
            yield {"type": "audio", "data": b"x"}
            yield {"type": "SentenceBoundary", "offset": 0, "duration": 20_000_000, "text": "First."}
            yield {"type": "SentenceBoundary", "offset": 15_000_000, "duration": 10_000_000, "text": "Second."}

        mock_comm = MagicMock()
        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            n = await tts._synthesize(
                "First. Second.", "TestVoice",
                tmp_path / "a.mp3", tmp_path / "a.srt",
            )
        return n

    n = asyncio.run(_run())
    assert n == 2


def test_synthesize_skips_empty_sentences(tmp_path):
    async def _run():
        async def fake_stream():
            yield {"type": "audio", "data": b"x"}
            yield {"type": "SentenceBoundary", "offset": 0, "duration": 5_000_000, "text": "  "}
            yield {"type": "SentenceBoundary", "offset": 5_000_000, "duration": 5_000_000, "text": "Real."}

        mock_comm = MagicMock()
        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            n = await tts._synthesize(
                "Real.", "TestVoice",
                tmp_path / "b.mp3", tmp_path / "b.srt",
            )
        return n

    n = asyncio.run(_run())
    assert n == 1


def test_run_synthesizes_chapter(tmp_path, monkeypatch):
    text_dir = tmp_path / "text"
    audio_dir = tmp_path / "audio"
    srt_dir = tmp_path / "srt"
    text_dir.mkdir()
    (text_dir / "chapter_001.txt").write_text("Hello world.", encoding="utf-8")

    monkeypatch.setattr(tts, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(tts, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(tts, "DIR_SRT", srt_dir)

    async def fake_stream():
        yield {"type": "audio", "data": b"mp3data"}
        yield {"type": "SentenceBoundary", "offset": 0, "duration": 10_000_000, "text": "Hello world."}

    mock_comm = MagicMock()
    mock_comm.stream = fake_stream

    with patch("edge_tts.Communicate", return_value=mock_comm):
        tts.run(voice="TestVoice")

    assert (audio_dir / "chapter_001.mp3").read_bytes() == b"mp3data"
    assert (srt_dir / "chapter_001.srt").exists()
