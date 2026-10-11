import asyncio
from unittest.mock import MagicMock, patch

import pytest

from miningcat.application.anki.config import save_config
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps import speech_synthesis
from miningcat.config.paths import paths
from miningcat.domain.languages import Language
from miningcat.infrastructure.speech import omnivoice_tts


def test_run_exits_if_no_text_dir(tmp_path, monkeypatch):
    with pytest.raises(ConverterError):
        speech_synthesis.run(voice="TestVoice")


def test_run_exits_if_no_text_files(tmp_path, monkeypatch):
    text_dir = paths.chapters_text
    text_dir.mkdir(parents=True)
    with pytest.raises(ConverterError):
        speech_synthesis.run(voice="TestVoice")


def test_run_skips_existing_files(tmp_path, monkeypatch):
    text_dir = paths.chapters_text
    audio_dir = paths.chapters_audio
    srt_dir = paths.srt
    text_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    srt_dir.mkdir(parents=True)
    (text_dir / "chapter_001.txt").write_text("Hello", encoding="utf-8")
    (audio_dir / "chapter_001.mp3").touch()
    (srt_dir / "chapter_001.srt").touch()


    with patch("edge_tts.Communicate") as mock_comm_cls:
        speech_synthesis.run(voice="TestVoice")
    mock_comm_cls.assert_not_called()


def test_synthesize_creates_files(tmp_path):
    async def _run():
        async def fake_stream():
            yield {"type": "audio", "data": b"audio_data"}
            yield {"type": "SentenceBoundary", "offset": 0, "duration": 10_000_000, "text": "Hello world."}

        mock_comm = MagicMock()
        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            n = await speech_synthesis._synthesize(
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
            n = await speech_synthesis._synthesize(
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
            n = await speech_synthesis._synthesize(
                "Real.", "TestVoice",
                tmp_path / "b.mp3", tmp_path / "b.srt",
            )
        return n

    n = asyncio.run(_run())
    assert n == 1


def test_run_synthesizes_chapter(tmp_path, monkeypatch):
    text_dir = paths.chapters_text
    audio_dir = paths.chapters_audio
    srt_dir = paths.srt
    text_dir.mkdir(parents=True)
    (text_dir / "chapter_001.txt").write_text("Hello world.", encoding="utf-8")


    async def fake_stream():
        yield {"type": "audio", "data": b"mp3data"}
        yield {"type": "SentenceBoundary", "offset": 0, "duration": 10_000_000, "text": "Hello world."}

    mock_comm = MagicMock()
    mock_comm.stream = fake_stream

    with patch("edge_tts.Communicate", return_value=mock_comm):
        speech_synthesis.run(voice="TestVoice")

    assert (audio_dir / "chapter_001.mp3").read_bytes() == b"mp3data"
    assert (srt_dir / "chapter_001.srt").exists()


@pytest.fixture
def fake_omnivoice(monkeypatch):
    """OmniVoice installed, reading each sentence in one second (the chapters it read: [(sentences, language, steps)])."""
    read = []

    def synthesize_chapter(sentences, language, audio_path, steps):
        read.append((sentences, language, steps))
        audio_path.write_bytes(b"omnivoice")
        return [(i, i + 1.0, sentence) for i, sentence in enumerate(sentences)]

    monkeypatch.setattr(omnivoice_tts, "installed", lambda: True)
    monkeypatch.setattr(omnivoice_tts, "synthesize_chapter", synthesize_chapter)
    return read


def _one_chapter(text="Hello world. Bye."):
    paths.chapters_text.mkdir(parents=True)
    (paths.chapters_text / "chapter_001.txt").write_text(text, encoding="utf-8")


def test_omnivoice_reads_the_chapters(fake_omnivoice):
    _one_chapter()
    with patch("edge_tts.Communicate") as edge:
        speech_synthesis.run(voice="fr-OmniVoice", lang=Language.FRENCH)
    edge.assert_not_called()
    assert fake_omnivoice == [(["Hello world.", "Bye."], "fr", 8)]
    assert (paths.chapters_audio / "chapter_001.mp3").read_bytes() == b"omnivoice"
    assert "Bye." in (paths.srt / "chapter_001.srt").read_text(encoding="utf-8")


def test_omnivoice_takes_over_when_edge_fails(fake_omnivoice):
    _one_chapter()
    save_config({"tts_steps": 16})
    with patch("edge_tts.Communicate", side_effect=RuntimeError("403, message='Invalid response status'")):
        speech_synthesis.run(voice="fr-FR-DeniseNeural", lang=Language.FRENCH)
    assert fake_omnivoice == [(["Hello world.", "Bye."], "fr", 16)]


def test_edge_failure_without_omnivoice(monkeypatch):
    _one_chapter()
    with patch("edge_tts.Communicate", side_effect=RuntimeError("403")), pytest.raises(RuntimeError, match="403"):
        speech_synthesis.run(voice="fr-FR-DeniseNeural", lang=Language.FRENCH)
