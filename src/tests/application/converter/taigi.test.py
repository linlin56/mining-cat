"""Taigi in the converter: its local speech engines, voice and writing systems."""
from pathlib import Path

import pytest

from miningcat.application.converter import options, speech_engines, transcription
from miningcat.application.converter.steps import script_conversion, speech_synthesis
from miningcat.application.mining import sentence_tts
from miningcat.domain.frequency_lists import character_list, word_frequency
from miningcat.domain.languages import Language, SpeechEngine
from miningcat.domain.ocr.plausibility import is_plausible_text
from miningcat.domain.subtitles.segment import Segment
from miningcat.domain.text.script_conversion import convert_text
from miningcat.domain.text.sentences import split_sentences
from miningcat.infrastructure.speech import mms_aligner, mms_tts, qwen3_asr
from miningcat.infrastructure.speech.local_models import SpeechError

from shared import redirect_path


def test_taigi_language():
    assert Language.from_id("taigi") is Language.TAIGI
    profile = Language.TAIGI.profile
    assert profile.transcriber is SpeechEngine.QWEN3_ASR and profile.aligner is SpeechEngine.MMS
    assert Language.MANDARIN_TW.profile.transcriber is SpeechEngine.WHISPER
    assert profile.tag == "nan-Hant" and Language.CANTONESE_HK.profile.tag == "yue-Hant" and Language.FRENCH.profile.tag == "fr-FR"


def test_split_sentences():
    text = "我欲去臺北食飯。「你好！」伊講。Lí hó! I kóng: hó. Pi 3.5 khoo.\n\n第二逝"
    assert split_sentences(text) == ["我欲去臺北食飯。", "「你好！」", "伊講。", "Lí hó!", "I kóng: hó.", "Pi 3.5 khoo.", "第二逝"]
    long = "一二三四五，六七八九十，一二三四五。"
    assert split_sentences(long, max_chars=8) == ["一二三四五，", "六七八九十，", "一二三四五。"]


def test_the_local_engines_of_taigi(monkeypatch):
    monkeypatch.setattr(qwen3_asr.Qwen3Asr, "load", classmethod(lambda cls, name: ("qwen", name)))
    monkeypatch.setattr(mms_aligner, "MmsAligner", lambda: "mms")
    assert speech_engines.load_transcriber("tiny", Language.TAIGI) == ("qwen", "tiny")
    assert speech_engines.load_aligner("tiny", Language.TAIGI) == "mms"


def test_chapters_of_taigi(tmp_path):
    class Transcriber:
        def transcribe(self, audio, lang):
            return [Segment(0, 0, 1, "我欲"), Segment(0, 1, 2, "。食飯")]
    segs = transcription.transcribe(Transcriber(), tmp_path / "a.mp3", Language.TAIGI)
    assert [s.text for s in segs] == ["我欲。", "食飯"]

    class Aligner:
        def align(self, audio, text, lang):
            return [Segment(0, i, i + 1, s) for i, s in enumerate(split_sentences(text))]
    text = tmp_path / "chapter_001.txt"
    text.write_text("我欲食飯[1]。\n你好！", encoding="utf-8")
    segs, length = transcription.align_chapter(Aligner(), tmp_path / "a.mp3", text, Language.TAIGI)
    assert [s.text for s in segs] == ["我欲食飯。", "你好！"] and length == len("我欲食飯。\n你好！")


def test_tts_run_with_a_local_voice(monkeypatch, tmp_path):
    text_dir, audio_dir, srt_dir = tmp_path / "text", tmp_path / "audio", tmp_path / "srt"
    text_dir.mkdir()
    (text_dir / "chapter_001.txt").write_text("我欲食飯。你好！", encoding="utf-8")
    redirect_path(monkeypatch, "chapters_text", text_dir)
    redirect_path(monkeypatch, "chapters_audio", audio_dir)
    redirect_path(monkeypatch, "srt", srt_dir)

    def chapter(sentences, voice, path):
        Path(path).write_bytes(b"mp3")
        return [(0.0, 1.0, sentences[0]), (1.3, 2.0, sentences[1])]
    monkeypatch.setattr(mms_tts, "synthesize_chapter", chapter)
    speech_synthesis.run(voice="nan-TW-MmsTaigi", lang=Language.TAIGI)
    srt = (srt_dir / "chapter_001.srt").read_text(encoding="utf-8")
    assert "我欲食飯。" in srt and "00:00:01,300 --> 00:00:02,000" in srt


def test_sentence_tts_with_a_local_voice(monkeypatch):
    assert {"id": "nan-TW-MmsTaigi", "label": "MMS - Taigi (local, Meta MMS-TTS)"} in sentence_tts.voices("nan")["voices"]
    assert sentence_tts.voices("nan")["default"] == "nan-TW-MmsTaigi"
    monkeypatch.setattr(mms_tts, "synthesize_mp3", lambda text, voice: b"mp3:" + text.encode())
    assert sentence_tts.synthesize("nan", "我欲食飯", "nan-TW-MmsTaigi") == "mp3:我欲食飯".encode()

    def fails(text, voice):
        raise SpeechError("There's nothing the voice can read in this text.")
    monkeypatch.setattr(mms_tts, "synthesize_mp3", fails)
    with pytest.raises(sentence_tts.TtsError, match="nothing"):
        sentence_tts.synthesize("nan", "123", "nan-TW-MmsTaigi")

    def offline(text, voice):
        raise OSError("no network")
    monkeypatch.setattr(mms_tts, "synthesize_mp3", offline)
    with pytest.raises(sentence_tts.TtsError, match="no network"):
        sentence_tts.synthesize("nan", "我", "nan-TW-MmsTaigi")


def test_converter_options_for_taigi():
    assert options.precision_values_for(Language.TAIGI) == options.QWEN3_PRECISION_VALUES
    assert [options.model_from_precision(v) for v in options.QWEN3_PRECISION_VALUES] == ["qwen3-0.6b", "qwen3-1.7b"]
    assert options.model_from_precision("Base (default)") == "base"
    assert options.model_for(None, Language.TAIGI) == "qwen3-0.6b"
    assert options.convert_labels_for(Language.TAIGI)[1:] == ["Hanji (漢字)", "Tâi-lô", "Pe̍h-ōe-jī (POJ)"]
    assert options.convert_target("Tâi-lô", Language.TAIGI) == "tailo"


def test_subtitles_conversion(tmp_path, monkeypatch):
    assert convert_text("chia̍h-pn̄g", "nan", "tailo") == "tsia̍h-pn̄g"
    with pytest.raises(ValueError):
        convert_text("guá", "nan", "s")
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nGóa beh chia̍h-pn̄g.\n", encoding="utf-8")
    redirect_path(monkeypatch, "srt", tmp_path)
    script_conversion.convert_srt_dir("nan", "tailo")
    assert "Guá beh tsia̍h-pn̄g." in srt.read_text(encoding="utf-8")


def test_qwen_output_is_written_in_traditional_characters(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(script_conversion, "convert_srt_file", lambda path, source, target: calls.append((source, target)))
    script_conversion.normalize_whisper_script(tmp_path / "a.srt", Language.TAIGI)
    assert calls == [("s", "tw")]


def test_taigi_ocr_and_frequency_tables():
    assert is_plausible_text("我欲食飯", Language.TAIGI) and is_plausible_text("Guá beh", Language.TAIGI)
    assert not is_plausible_text("123 !!", Language.TAIGI)
    assert character_list.supports_language(Language.TAIGI)
    assert word_frequency.compute("guá beh, guá", Language.TAIGI)["guá"] == 2
