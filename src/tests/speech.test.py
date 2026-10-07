import sys
import types
from pathlib import Path

import numpy as np
import pytest

import speech
from language import Language, split_sentences
from speech import mms_align, mms_tts, qwen3

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------- shared helpers

def test_require_explains_how_to_install():
    assert speech.require("json", "Reading JSON").dumps([]) == "[]"
    with pytest.raises(speech.SpeechError, match="make install-taigi"):
        speech.require("no_such_package_here", "Something")


def test_mp3_round_trip(tmp_path):
    tone = np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000).astype(np.float32) * 0.5
    path = tmp_path / "tone.mp3"
    speech.encode_mp3(tone, 16000, path)
    assert path.stat().st_size > 1000
    assert speech.encode_mp3(tone, 16000)[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    samples = speech.load_audio(path)
    assert abs(len(samples) - 16000) < 3000 and samples.dtype == np.float32


def test_unreadable_audio(tmp_path):
    (tmp_path / "bad.mp3").write_bytes(b"not audio")
    with pytest.raises(speech.SpeechError, match="ffmpeg"):
        speech.load_audio(tmp_path / "bad.mp3")


def test_torch_device(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert speech.torch_device() == "cuda"
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    assert speech.torch_device() == "mps"
    assert speech.torch_device(allow_mps=False) == "cpu"


# ---------------------------------------------------------------- language

def test_taigi_language():
    assert Language.from_id("taigi") is Language.TAIGI
    assert Language.TAIGI.value.asr == "qwen3" and Language.TAIGI.value.aligner == "mms"
    assert Language.MANDARIN_TW.value.asr == "whisper"
    assert Language.TAIGI.tag == "nan-Hant" and Language.CANTONESE_HK.tag == "yue-Hant" and Language.FRENCH.tag == "fr-FR"


def test_split_sentences():
    text = "我欲去臺北食飯。「你好！」伊講。Lí hó! I kóng: hó. Pi 3.5 khoo.\n\n第二逝"
    assert split_sentences(text) == ["我欲去臺北食飯。", "「你好！」", "伊講。", "Lí hó!", "I kóng: hó.", "Pi 3.5 khoo.", "第二逝"]
    long = "一二三四五，六七八九十，一二三四五。"
    assert split_sentences(long, max_chars=8) == ["一二三四五，", "六七八九十，", "一二三四五。"]


# ---------------------------------------------------------------- Qwen3-ASR

def test_model_names():
    assert qwen3.model_name("qwen3-1.7b") == "qwen3-1.7b"
    assert qwen3.model_name("large") == qwen3.model_name("turbo") == "qwen3-1.7b"
    assert qwen3.model_name("tiny") == qwen3.model_name(None) == "qwen3-0.6b"


def test_times_are_shared_between_sentences():
    timed = qwen3._split_times("我欲食飯。你好！", 1.0, 3.0)
    assert [t[2] for t in timed] == ["我欲食飯。", "你好！"]
    assert timed[0][0] == 1.0 and timed[-1][1] == pytest.approx(3.0)
    assert timed[0][1] == pytest.approx(1.0 + 2.0 * 5 / 8)
    long = qwen3._split_times("一二三四五六七八九十，一二三四五六七八九十。", 0, 1, max_chars=12)
    assert [t[2] for t in long] == ["一二三四五六七八九十，", "一二三四五六七八九十。"]


class FakeQwen:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language=None, context=""):
        self.calls.append((len(audio), language, context))
        return [types.SimpleNamespace(text="我欲食飯。" if i % 2 == 0 else "") for i in range(len(audio))]


def test_transcribe(monkeypatch):
    monkeypatch.setattr(qwen3, "load_audio", lambda path: np.zeros(16000 * 30, dtype=np.float32))
    monkeypatch.setattr(qwen3, "utterances", lambda samples: [(i * 16000, i * 16000 + 8000) for i in range(10)])
    model = FakeQwen()
    segments = qwen3.transcribe(model, "audio.mp3", "nan", progress=False)
    assert [c[0] for c in model.calls] == [8, 2]
    assert model.calls[0][1:] == ("Chinese", "台語（閩南語）")
    assert len(segments) == 5 and segments[1].start == 2.0 and segments[1].end == 2.5 and segments[1].text == "我欲食飯。"


def test_transcribe_without_speech_or_with_errors(monkeypatch):
    monkeypatch.setattr(qwen3, "load_audio", lambda path: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(qwen3, "utterances", lambda samples: [])
    assert qwen3.transcribe(FakeQwen(), "audio.mp3") == []
    monkeypatch.setattr(qwen3, "utterances", lambda samples: [(0, 8000)])

    class Broken:
        def transcribe(self, **kwargs):
            raise MemoryError("out of memory")
    with pytest.raises(speech.SpeechError, match="out of memory"):
        qwen3.transcribe(Broken(), "audio.mp3", progress=False)


def test_utterances_of_silence():
    pytest.importorskip("faster_whisper")
    assert qwen3.utterances(np.zeros(16000 * 2, dtype=np.float32)) == []


def test_load_model(monkeypatch):
    loaded = {}

    class Model:
        @classmethod
        def from_pretrained(cls, repo, **kwargs):
            loaded.update(repo=repo, **kwargs)
            return cls()

    monkeypatch.setitem(sys.modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=Model))
    monkeypatch.setitem(sys.modules, "nagisa", None)  # not installed: a placeholder replaces it
    monkeypatch.setattr(qwen3, "torch_device", lambda: "cpu")
    assert isinstance(qwen3.load_model("large"), Model)
    assert loaded["repo"] == "Qwen/Qwen3-ASR-1.7B" and loaded["device_map"] == "cpu" and loaded["dtype"] is torch.float32


def test_missing_qwen_asr(monkeypatch):
    monkeypatch.setitem(sys.modules, "qwen_asr", None)
    with pytest.raises(speech.SpeechError, match="make install-taigi"):
        qwen3.load_model()


# ---------------------------------------------------------------- MMS aligner

def emission_for(frames: list[int], vocabulary: int = 6) -> np.ndarray:
    """Log-probabilities where each frame clearly says one token (0 = blank)."""
    probs = np.full((len(frames), vocabulary), 0.01)
    for t, token in enumerate(frames):
        probs[t, token] = 1.0
    return np.log(probs / probs.sum(axis=1, keepdims=True)).astype(np.float32)


def test_token_spans():
    emission = emission_for([0, 1, 1, 0, 2, 0, 0, 2, 3, 0])
    assert mms_align._token_spans(emission, [1, 2, 2, 3]) == [(1, 2), (4, 4), (7, 7), (8, 8)]
    assert mms_align._token_spans(emission[:2], [1, 2, 3]) is None   # more tokens than frames
    assert mms_align._token_spans(emission[:3], [2, 2, 2]) is None   # a repeat needs a blank between
    assert mms_align._token_spans(emission, []) is None


def test_align_emission_a_few_sentences_at_a_time(monkeypatch):
    monkeypatch.setattr(mms_align, "GROUP_LETTERS", 2)
    monkeypatch.setattr(mms_align, "WINDOW_EXTRA_FRAMES", 2)
    frames = [0, 1, 1, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 0, 4, 0, 0, 5, 5, 0]
    units = [("一", [1]), ("二", [2]), ("三", [3]), ("四", [4]), ("五", [5])]
    timed = mms_align.align_emission(emission_for(frames), units)
    assert [t[2] for t in timed] == ["一", "二", "三", "四", "五"]
    starts = [round(t[0] / mms_align.FRAME_SECONDS) for t in timed]
    assert starts == [1, 5, 10, 14, 17]
    assert round(timed[0][1] / mms_align.FRAME_SECONDS) == 3


def test_align_emission_errors():
    with pytest.raises(speech.SpeechError, match="empty"):
        mms_align.align_emission(np.zeros((0, 6), dtype=np.float32), [("一", [1])])
    with pytest.raises(speech.SpeechError, match="longer than its audio"):
        mms_align.align_emission(emission_for([0, 1]), [("一", [1, 2, 3, 4])])


def test_latin_romanizer():
    assert mms_align._romanizer("fr")("Où est-il ?") == "ou est il"


class FakeBundle:
    sample_rate = 16000

    @staticmethod
    def get_dict(star=None):
        return {"-": 0, "a": 1, "g": 2, "u": 3, "b": 4, "e": 5, "h": 6}

    @staticmethod
    def get_model(with_star=False):
        class Model(torch.nn.Module):
            def forward(self, waveform):
                frames = (waveform.shape[1] - 400) // 320 + 1
                return torch.zeros(1, frames, 7), None
        return Model()


def test_aligner(monkeypatch):
    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace(pipelines=types.SimpleNamespace(MMS_FA=FakeBundle)))
    aligner = mms_align.Aligner()
    samples = np.zeros(16000 * 70, dtype=np.float32)
    emission = aligner.emissions(samples)
    assert emission.shape == (3500, 7)  # 70 s, the windows' frames counted exactly
    assert aligner.tokens("gua beh") == [2, 3, 1, 4, 5, 6]

    monkeypatch.setattr(mms_align, "load_audio", lambda path: np.zeros(16000 * 4, dtype=np.float32))
    timed = aligner.align("audio.mp3", ["「", "Guá", "123", "beh."], "nan", progress=False)
    assert [t[2] for t in timed] == ["「Guá123", "beh."]
    assert timed[0][0] < timed[1][0]
    assert aligner.align("audio.mp3", ["123"], "nan") == []


# ---------------------------------------------------------------- MMS voice

class FakeVits:
    config = types.SimpleNamespace(sampling_rate=16000)

    def eval(self):
        return self

    def __call__(self, input_ids):
        return types.SimpleNamespace(waveform=torch.ones(1, 1600 * input_ids.shape[-1]) * 0.1)


class FakeTokenizer:
    def __call__(self, text, return_tensors="pt"):
        letters = [c for c in text if c.isalpha()]
        return {"input_ids": torch.zeros(1, 2 * len(letters) + 1, dtype=torch.long)}


@pytest.fixture
def fake_voice(monkeypatch):
    texts = []

    class Tokenizer(FakeTokenizer):
        def __call__(self, text, return_tensors="pt"):
            texts.append(text)
            return super().__call__(text, return_tensors)

    monkeypatch.setitem(sys.modules, "transformers", types.SimpleNamespace(
        VitsModel=types.SimpleNamespace(from_pretrained=lambda repo: FakeVits()),
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda repo: Tokenizer()),
    ))
    mms_tts._models.clear()
    yield texts
    mms_tts._models.clear()


def test_synthesize(fake_voice):
    samples, rate = mms_tts.synthesize("Guá beh tsia̍h-pn̄g.", "nan-TW-MmsTaigi")
    assert rate == 16000 and len(samples) > 0
    assert fake_voice == ["Góa beh chia̍h-pn̄g."]  # the voice reads POJ
    assert len(mms_tts.synthesize("123", "nan-TW-MmsTaigi")[0]) == 0
    with pytest.raises(speech.SpeechError, match="Unknown local voice"):
        mms_tts.synthesize("a", "fr-FR-DeniseNeural")
    assert mms_tts.synthesize_mp3("guá", "nan-TW-MmsTaigi")[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    with pytest.raises(speech.SpeechError, match="nothing"):
        mms_tts.synthesize_mp3("123", "nan-TW-MmsTaigi")


def test_synthesize_chapter(fake_voice, tmp_path):
    path = tmp_path / "chapter.mp3"
    timed = mms_tts.synthesize_chapter(["guá.", "123", "beh."], "nan-TW-MmsTaigi", path)
    assert [t[2] for t in timed] == ["guá.123", "beh."]
    assert timed[1][0] == pytest.approx(timed[0][1] + mms_tts.PAUSE_SECONDS)
    assert path.stat().st_size > 0
    with pytest.raises(speech.SpeechError):
        mms_tts.synthesize_chapter(["123"], "nan-TW-MmsTaigi", tmp_path / "empty.mp3")


# ---------------------------------------------------------------- the pipeline with the local engines

def test_align_dispatches_to_the_local_engines(monkeypatch, tmp_path):
    import align

    monkeypatch.setattr(qwen3, "load_model", lambda name: ("qwen", name))
    monkeypatch.setattr(mms_align, "Aligner", lambda: "mms")
    assert align.load_asr_model("tiny", Language.TAIGI) == ("qwen", "tiny")
    assert align.load_aligner("tiny", Language.TAIGI) == "mms"
    assert align.language_key_of(Language.TAIGI) == "nan" and align.language_key_of(Language.CANTONESE_HK) == "yue"

    monkeypatch.setattr(qwen3, "transcribe", lambda model, audio, language: [
        align.Segment(0, 0, 1, "我欲"), align.Segment(0, 1, 2, "。食飯")])
    segs = align.transcribe_chapter("model", tmp_path / "a.mp3", Language.TAIGI)
    assert [s.text for s in segs] == ["我欲。", "食飯"]

    class Aligner:
        def align(self, audio, sentences, language):
            assert language == "nan"
            return [(i, i + 1, s) for i, s in enumerate(sentences)]
    text = tmp_path / "chapter_001.txt"
    text.write_text("我欲食飯[1]。\n你好！", encoding="utf-8")
    segs, length = align.align_chapter(Aligner(), tmp_path / "a.mp3", text, Language.TAIGI)
    assert [s.text for s in segs] == ["我欲食飯。", "你好！"] and length == len("我欲食飯。\n你好！")


def test_tts_run_with_a_local_voice(monkeypatch, tmp_path):
    import tts

    text_dir, audio_dir, srt_dir = tmp_path / "text", tmp_path / "audio", tmp_path / "srt"
    text_dir.mkdir()
    (text_dir / "chapter_001.txt").write_text("我欲食飯。你好！", encoding="utf-8")
    monkeypatch.setattr(tts, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(tts, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(tts, "DIR_SRT", srt_dir)

    def chapter(sentences, voice, path):
        Path(path).write_bytes(b"mp3")
        return [(0.0, 1.0, sentences[0]), (1.3, 2.0, sentences[1])]
    monkeypatch.setattr(mms_tts, "synthesize_chapter", chapter)
    tts.run(voice="nan-TW-MmsTaigi", lang=Language.TAIGI)
    srt = (srt_dir / "chapter_001.srt").read_text(encoding="utf-8")
    assert "我欲食飯。" in srt and "00:00:01,300 --> 00:00:02,000" in srt


def test_sentence_tts_with_a_local_voice(monkeypatch):
    from mining import sentence_tts

    assert {"id": "nan-TW-MmsTaigi", "label": "MMS - Taigi (local, Meta MMS-TTS)"} in sentence_tts.voices("nan")["voices"]
    assert sentence_tts.voices("nan")["default"] == "nan-TW-MmsTaigi"
    monkeypatch.setattr(mms_tts, "synthesize_mp3", lambda text, voice: b"mp3:" + text.encode())
    assert sentence_tts.synthesize("nan", "我欲食飯", "nan-TW-MmsTaigi") == "mp3:我欲食飯".encode()

    def fails(text, voice):
        raise speech.SpeechError("There's nothing the voice can read in this text.")
    monkeypatch.setattr(mms_tts, "synthesize_mp3", fails)
    with pytest.raises(sentence_tts.TtsError, match="nothing"):
        sentence_tts.synthesize("nan", "123", "nan-TW-MmsTaigi")

    def offline(text, voice):
        raise OSError("no network")
    monkeypatch.setattr(mms_tts, "synthesize_mp3", offline)
    with pytest.raises(sentence_tts.TtsError, match="no network"):
        sentence_tts.synthesize("nan", "我", "nan-TW-MmsTaigi")


def test_converter_options_for_taigi():
    from web import options

    assert options.precision_values_for(Language.TAIGI) == options.QWEN3_PRECISION_VALUES
    assert [options.model_from_precision(v) for v in options.QWEN3_PRECISION_VALUES] == ["qwen3-0.6b", "qwen3-1.7b"]
    assert options.model_from_precision("Base (default)") == "base"
    assert options.convert_labels_for(Language.TAIGI)[1:] == ["Hanji (漢字)", "Tâi-lô", "Pe̍h-ōe-jī (POJ)"]


def test_subtitles_conversion(tmp_path, monkeypatch):
    import chinese_converter

    assert chinese_converter.convert_text("chia̍h-pn̄g", "nan", "tailo") == "tsia̍h-pn̄g"
    with pytest.raises(ValueError):
        chinese_converter.convert_text("guá", "nan", "s")
    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nGóa beh chia̍h-pn̄g.\n", encoding="utf-8")
    monkeypatch.setattr(chinese_converter, "DIR_SRT", tmp_path)
    chinese_converter.convert_srt_dir("nan", "tailo")
    assert "Guá beh tsia̍h-pn̄g." in srt.read_text(encoding="utf-8")


def test_qwen_output_is_written_in_traditional_characters(tmp_path, monkeypatch):
    import chinese_converter

    calls = []
    monkeypatch.setattr(chinese_converter, "convert_srt_file", lambda path, source, target: calls.append((source, target)))
    chinese_converter.normalize_whisper_script(tmp_path / "a.srt", Language.TAIGI)
    assert calls == [("s", "tw")]


def test_taigi_ocr_and_frequency_tables():
    from frequency import character_frequency, word_frequency
    from ocr_mining.dedup import is_plausible_text

    assert is_plausible_text("我欲食飯", Language.TAIGI) and is_plausible_text("Guá beh", Language.TAIGI)
    assert not is_plausible_text("123 !!", Language.TAIGI)
    assert character_frequency.supports_language(Language.TAIGI)
    assert word_frequency.compute("guá beh, guá", Language.TAIGI)["guá"] == 2
