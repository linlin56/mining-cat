import pytest

from miningcat.application.converter import speech_engines
from miningcat.application.converter.errors import ConverterError
from miningcat.domain.languages import Language, SpeechEngine
from miningcat.infrastructure.speech import qwen3_asr


@pytest.fixture
def engines(monkeypatch):
    monkeypatch.setattr(qwen3_asr.Qwen3Asr, "load", classmethod(lambda cls, name: ("qwen", name)))
    monkeypatch.setattr(speech_engines, "_whisper", lambda name, lang: ("whisper", name))


def test_qwen3_asr_replaces_whisper_when_asked(engines):
    assert speech_engines.load_transcriber("base", Language.JAPANESE) == ("whisper", "base")
    assert speech_engines.load_transcriber("qwen3-1.7b", Language.JAPANESE) == ("qwen", "qwen3-1.7b")
    assert speech_engines.load_transcriber("qwen3-0.6b", Language.FRENCH) == ("qwen", "qwen3-0.6b")


def test_transcriber_engine():
    assert speech_engines.transcriber_engine("base", Language.FRENCH) is SpeechEngine.WHISPER
    assert speech_engines.transcriber_engine("qwen3-0.6b", Language.FRENCH) is SpeechEngine.QWEN3_ASR
    assert speech_engines.transcriber_engine("tiny", Language.TAIGI) is SpeechEngine.QWEN3_ASR


def test_qwen3_asr_needs_a_language_it_knows(engines, monkeypatch):
    monkeypatch.setattr(qwen3_asr, "QWEN_LANGUAGES", {})
    with pytest.raises(ConverterError, match="Whisper model"):
        speech_engines.load_transcriber("qwen3-0.6b", Language.FRENCH)


def test_a_book_is_aligned_with_whisper(engines):
    assert speech_engines.load_aligner("small", Language.FRENCH) == ("whisper", "small")
    with pytest.raises(ConverterError, match="only transcribes"):
        speech_engines.load_aligner("qwen3-0.6b", Language.FRENCH)
