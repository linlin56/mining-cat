import json
import subprocess
import sys
import types

import numpy as np
import pytest

from miningcat.config.paths import paths
from miningcat.domain.languages import LANGUAGES, Language
from miningcat.domain.text import taigi
from miningcat.infrastructure.speech import (
    local_models, mms_aligner, mms_tts, omnivoice_tts, omnivoice_worker, qwen3_asr,
)

torch = pytest.importorskip("torch")


def test_require_explains_how_to_install():
    assert local_models.require("json", "Reading JSON").dumps([]) == "[]"
    with pytest.raises(local_models.SpeechError, match="make install-qwen"):
        local_models.require("no_such_package_here", "Something")


def test_local_model(monkeypatch, tmp_path):
    hub = pytest.importorskip("huggingface_hub")
    asked = []

    def snapshot_download(repo, local_files_only=False):
        asked.append(local_files_only)
        if repo != "org/cached":
            raise hub.errors.LocalEntryNotFoundError("not in the cache")
        return str(tmp_path)

    monkeypatch.setattr(hub, "snapshot_download", snapshot_download)
    assert local_models.local_model("org/cached") == str(tmp_path)
    assert local_models.local_model("org/missing") == "org/missing"  # downloaded when it's loaded
    assert asked == [True, True]  # never asks huggingface.co


def test_mp3_round_trip(tmp_path):
    tone = np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000).astype(np.float32) * 0.5
    path = tmp_path / "tone.mp3"
    local_models.encode_mp3(tone, 16000, path)
    assert path.stat().st_size > 1000
    assert local_models.encode_mp3(tone, 16000)[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    samples = local_models.load_audio(path)
    assert abs(len(samples) - 16000) < 3000 and samples.dtype == np.float32


def test_unreadable_audio(tmp_path):
    (tmp_path / "bad.mp3").write_bytes(b"not audio")
    with pytest.raises(local_models.SpeechError, match="ffmpeg"):
        local_models.load_audio(tmp_path / "bad.mp3")


def test_torch_device(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert local_models.torch_device() == "cuda"
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    assert local_models.torch_device() == "mps"
    assert local_models.torch_device(allow_mps=False) == "cpu"


def test_model_names():
    assert qwen3_asr.model_name("qwen3-1.7b") == "qwen3-1.7b"
    assert qwen3_asr.model_name("large") == qwen3_asr.model_name("turbo") == "qwen3-1.7b"
    assert qwen3_asr.model_name("tiny") == qwen3_asr.model_name(None) == "qwen3-0.6b"


def test_times_are_shared_between_sentences():
    timed = qwen3_asr._split_times("我欲食飯。你好！", 1.0, 3.0)
    assert [t[2] for t in timed] == ["我欲食飯。", "你好！"]
    assert timed[0][0] == 1.0 and timed[-1][1] == pytest.approx(3.0)
    assert timed[0][1] == pytest.approx(1.0 + 2.0 * 5 / 8)
    long = qwen3_asr._split_times("一二三四五六七八九十，一二三四五六七八九十。", 0, 1, max_chars=12)
    assert [t[2] for t in long] == ["一二三四五六七八九十，", "一二三四五六七八九十。"]
    latin = qwen3_asr._split_times("Il fait 3.5 degrés. Tu viens ? Oui, j'arrive, attends-moi.", 0, 1, max_chars=20)
    assert [t[2] for t in latin] == ["Il fait 3.5 degrés.", "Tu viens ?", "Oui, j'arrive,", "attends-moi."]


def test_languages_of_qwen3_asr(monkeypatch):
    assert all(qwen3_asr.supports(lang) for lang in Language)
    assert qwen3_asr.is_model("Qwen3-1.7B") and not qwen3_asr.is_model("large") and not qwen3_asr.is_model(None)
    monkeypatch.setattr(qwen3_asr.importlib.util, "find_spec", lambda name: None)
    assert not qwen3_asr.installed()


class FakeQwen:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language=None, context=""):
        self.calls.append((len(audio), language, context))
        return [types.SimpleNamespace(text="我欲食飯。" if i % 2 == 0 else "") for i in range(len(audio))]


def test_transcribe(monkeypatch):
    monkeypatch.setattr(qwen3_asr, "load_audio", lambda path: np.zeros(16000 * 30, dtype=np.float32))
    monkeypatch.setattr(qwen3_asr, "utterances", lambda samples: [(i * 16000, i * 16000 + 8000) for i in range(10)])
    model = FakeQwen()
    segments = qwen3_asr.transcribe(model, "audio.mp3", "nan", progress=False)
    assert [c[0] for c in model.calls] == [8, 2]
    assert model.calls[0][1:] == ("Chinese", "")  # a context is written out as is
    assert len(segments) == 5 and segments[1].start == 2.0 and segments[1].end == 2.5 and segments[1].text == "我欲食飯。"


def test_transcribe_without_speech_or_with_errors(monkeypatch):
    monkeypatch.setattr(qwen3_asr, "load_audio", lambda path: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(qwen3_asr, "utterances", lambda samples: [])
    assert qwen3_asr.transcribe(FakeQwen(), "audio.mp3") == []
    monkeypatch.setattr(qwen3_asr, "utterances", lambda samples: [(0, 8000)])

    class Broken:
        def transcribe(self, **kwargs):
            raise MemoryError("out of memory")
    with pytest.raises(local_models.SpeechError, match="out of memory"):
        qwen3_asr.transcribe(Broken(), "audio.mp3", progress=False)


def test_utterances_of_silence():
    pytest.importorskip("faster_whisper")
    assert qwen3_asr.utterances(np.zeros(16000 * 2, dtype=np.float32)) == []


def test_load_model(monkeypatch):
    loaded = {}

    class Model:
        @classmethod
        def from_pretrained(cls, repo, **kwargs):
            loaded.update(repo=repo, **kwargs)
            return cls()

    monkeypatch.setitem(sys.modules, "qwen_asr", types.SimpleNamespace(Qwen3ASRModel=Model))
    monkeypatch.setitem(sys.modules, "nagisa", None)  # not installed: a placeholder replaces it
    monkeypatch.setattr(qwen3_asr, "torch_device", lambda: "cpu")
    monkeypatch.setattr(qwen3_asr, "local_model", lambda repo: repo)
    assert isinstance(qwen3_asr.load_model("large"), Model)
    assert loaded["repo"] == "Qwen/Qwen3-ASR-1.7B" and loaded["device_map"] == "cpu" and loaded["dtype"] is torch.float32


def test_missing_qwen_asr(monkeypatch):
    monkeypatch.setitem(sys.modules, "qwen_asr", None)
    with pytest.raises(local_models.SpeechError, match="make install-qwen"):
        qwen3_asr.load_model()


def emission_for(frames: list[int], vocabulary: int = 6) -> np.ndarray:
    """Log-probabilities where each frame clearly says one token (0 = blank)."""
    probs = np.full((len(frames), vocabulary), 0.01)
    for t, token in enumerate(frames):
        probs[t, token] = 1.0
    return np.log(probs / probs.sum(axis=1, keepdims=True)).astype(np.float32)


def test_token_spans():
    emission = emission_for([0, 1, 1, 0, 2, 0, 0, 2, 3, 0])
    assert mms_aligner._token_spans(emission, [1, 2, 2, 3]) == [(1, 2), (4, 4), (7, 7), (8, 8)]
    assert mms_aligner._token_spans(emission[:2], [1, 2, 3]) is None   # more tokens than frames
    assert mms_aligner._token_spans(emission[:3], [2, 2, 2]) is None   # a repeat needs a blank between
    assert mms_aligner._token_spans(emission, []) is None


def test_align_emission_a_few_sentences_at_a_time(monkeypatch):
    monkeypatch.setattr(mms_aligner, "GROUP_LETTERS", 2)
    monkeypatch.setattr(mms_aligner, "WINDOW_EXTRA_FRAMES", 2)
    frames = [0, 1, 1, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 0, 4, 0, 0, 5, 5, 0]
    units = [("一", [1]), ("二", [2]), ("三", [3]), ("四", [4]), ("五", [5])]
    timed = mms_aligner.align_emission(emission_for(frames), units)
    assert [t[2] for t in timed] == ["一", "二", "三", "四", "五"]
    starts = [round(t[0] / mms_aligner.FRAME_SECONDS) for t in timed]
    assert starts == [1, 5, 10, 14, 17]
    assert round(timed[0][1] / mms_aligner.FRAME_SECONDS) == 3


def test_align_emission_errors():
    with pytest.raises(local_models.SpeechError, match="empty"):
        mms_aligner.align_emission(np.zeros((0, 6), dtype=np.float32), [("一", [1])])
    with pytest.raises(local_models.SpeechError, match="longer than its audio"):
        mms_aligner.align_emission(emission_for([0, 1]), [("一", [1, 2, 3, 4])])


def test_latin_romanizer():
    assert mms_aligner._romanizer("fr")("Où est-il ?") == "ou est il"


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
    aligner = mms_aligner.MmsAligner()
    samples = np.zeros(16000 * 70, dtype=np.float32)
    emission = aligner.emissions(samples)
    assert emission.shape == (3500, 7)  # 70 s, the windows' frames counted exactly
    assert aligner.tokens("gua beh") == [2, 3, 1, 4, 5, 6]

    monkeypatch.setattr(mms_aligner, "load_audio", lambda path: np.zeros(16000 * 4, dtype=np.float32))
    timed = aligner.align_sentences("audio.mp3", ["「", "Guá", "123", "beh."], "nan", progress=False)
    assert [t[2] for t in timed] == ["「Guá123", "beh."]
    assert timed[0][0] < timed[1][0]
    assert aligner.align_sentences("audio.mp3", ["123"], "nan") == []


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
    monkeypatch.setattr(mms_tts, "local_model", lambda repo: repo)
    mms_tts._models.clear()
    yield texts
    mms_tts._models.clear()


def test_synthesize(fake_voice):
    samples, rate = mms_tts.synthesize("Guá beh tsia̍h-pn̄g.", "nan-TW-MmsTaigi")
    assert rate == 16000 and len(samples) > 0
    assert fake_voice == ["Góa beh chia̍h-pn̄g."]  # the voice reads POJ
    assert len(mms_tts.synthesize("123", "nan-TW-MmsTaigi")[0]) == 0
    with pytest.raises(local_models.SpeechError, match="Unknown local voice"):
        mms_tts.synthesize("a", "fr-FR-DeniseNeural")
    assert mms_tts.synthesize_mp3("guá", "nan-TW-MmsTaigi")[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    with pytest.raises(local_models.SpeechError, match="nothing"):
        mms_tts.synthesize_mp3("123", "nan-TW-MmsTaigi")


def test_preload(fake_voice, monkeypatch):
    started = []
    monkeypatch.setattr(mms_tts.threading, "Thread", lambda target, args, daemon: types.SimpleNamespace(
        start=lambda: started.append(args) or target(*args)))
    mms_tts.preload("fr-FR-DeniseNeural")  # an Edge voice: nothing to load
    mms_tts.preload("")
    assert started == [] and not mms_tts._models
    mms_tts.preload("nan-TW-MmsTaigi")
    assert "nan-TW-MmsTaigi" in mms_tts._models
    mms_tts.preload("nan-TW-MmsTaigi")  # already loaded
    assert started == [("nan-TW-MmsTaigi",)]


def test_preload_errors_are_left_to_the_reading(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    mms_tts._models.clear()
    mms_tts._preload("nan-TW-MmsTaigi")  # doesn't raise in the thread
    with pytest.raises(local_models.SpeechError, match="make install-taigi"):
        mms_tts.synthesize("guá", "nan-TW-MmsTaigi")


def test_synthesize_chapter(fake_voice, tmp_path):
    path = tmp_path / "chapter.mp3"
    timed = mms_tts.synthesize_chapter(["guá.", "123", "beh."], "nan-TW-MmsTaigi", path)
    assert [t[2] for t in timed] == ["guá.123", "beh."]
    assert timed[1][0] == pytest.approx(timed[0][1] + mms_tts.PAUSE_SECONDS)
    assert path.stat().st_size > 0
    with pytest.raises(local_models.SpeechError):
        mms_tts.synthesize_chapter(["123"], "nan-TW-MmsTaigi", tmp_path / "empty.mp3")


def test_aligner_gives_the_subtitles_of_the_text(monkeypatch):
    monkeypatch.setitem(sys.modules, "torchaudio", types.SimpleNamespace(pipelines=types.SimpleNamespace(MMS_FA=FakeBundle)))
    aligner = mms_aligner.MmsAligner()
    monkeypatch.setattr(aligner, "align_sentences", lambda audio, sentences, language: [
        (i, i + 1, s) for i, s in enumerate(sentences)])
    segs = aligner.align("audio.mp3", "我欲食飯。你好！", Language.TAIGI)
    assert [(s.start, s.text) for s in segs] == [(0, "我欲食飯。"), (1, "你好！")]


def test_qwen3_asr_transcribes_in_the_language(monkeypatch):
    monkeypatch.setattr(qwen3_asr, "load_model", lambda name: ("model", name))
    asked = []
    monkeypatch.setattr(qwen3_asr, "transcribe",
                        lambda model, audio, language, max_chars: asked.append((model, language, max_chars)) or [])
    transcriber = qwen3_asr.Qwen3Asr.load("large")
    assert transcriber.name == "Qwen3-ASR" and transcriber.transcribe("a.mp3", Language.TAIGI) == []
    transcriber.transcribe("a.mp3", Language.FRENCH)
    assert asked == [(("model", "large"), "nan", 30), (("model", "large"), "fr", 80)]



def test_engine_install_commands(monkeypatch):
    from miningcat.infrastructure.speech import engine_install
    ran = []
    monkeypatch.setattr(engine_install.pip.subprocess, "run",
                        lambda command, check: ran.append(command[4:]) or types.SimpleNamespace(returncode=0))
    assert engine_install.install(engine_install.QWEN) == 0
    qwen = [["-r", str(engine_install.PROJECT_ROOT / "requirements-qwen.txt")],
            ["--no-deps", engine_install.QWEN_ASR_REQUIREMENT]]
    assert ran == qwen
    ran.clear()
    assert engine_install.install(engine_install.TAIGI) == 0  # Qwen3-ASR transcribes Taigi, then MMS
    assert ran == qwen + [["-r", str(engine_install.PROJECT_ROOT / "requirements-taigi.txt")]]


def test_engine_install_stops_at_the_first_failure(monkeypatch):
    from miningcat.infrastructure.speech import engine_install
    ran = []
    monkeypatch.setattr(engine_install.pip.subprocess, "run",
                        lambda command, check: ran.append(command) or types.SimpleNamespace(returncode=1))
    assert engine_install.install(engine_install.TAIGI) == 1 and len(ran) == 1


def test_engines_installed(monkeypatch):
    from miningcat.infrastructure.speech import engine_install
    monkeypatch.setattr(qwen3_asr, "installed", lambda: False)
    assert not engine_install.installed(engine_install.QWEN) and not engine_install.installed(engine_install.TAIGI)
    monkeypatch.setattr(qwen3_asr, "installed", lambda: True)
    monkeypatch.setitem(sys.modules, "transformers", None)
    monkeypatch.setattr(engine_install.importlib.util, "find_spec", lambda name: None)
    assert engine_install.installed(engine_install.QWEN) and not engine_install.installed(engine_install.TAIGI)


def test_omnivoice_install_commands(monkeypatch):
    from miningcat.infrastructure.speech import engine_install
    monkeypatch.setattr(engine_install.pip.platform, "system", lambda: "Linux")
    monkeypatch.setattr(engine_install.pip.shutil, "which", lambda name: None)  # no NVIDIA GPU
    venv, pip = str(omnivoice_tts.VENV), [str(omnivoice_tts.PYTHON), "-m", "pip", "install"]
    assert engine_install.commands(engine_install.OMNIVOICE) == [
        [engine_install.PYTHON, "-m", "venv", venv],  # its own environment: it needs transformers 5
        [*pip, "torch", "torchaudio", "--index-url", engine_install.pip.PYTORCH_CPU_INDEX],
        [*pip, "-r", str(engine_install.PROJECT_ROOT / "requirements-omnivoice.txt")],
        [*pip, "--no-deps", engine_install.OMNIVOICE_REQUIREMENT],
        [str(omnivoice_tts.PYTHON), "-c", "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice')"],
    ]
    monkeypatch.setattr(engine_install.pip.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    assert engine_install.commands(engine_install.OMNIVOICE)[1] == [*pip, "torch", "torchaudio"]
    assert not engine_install.installed(engine_install.OMNIVOICE)  # conftest: never the real one
    monkeypatch.setattr(omnivoice_tts, "installed", lambda: True)
    assert engine_install.installed(engine_install.OMNIVOICE)


def test_omnivoice_text():
    pytest.importorskip("opencc")
    # Traditional characters get Cantonese readings: Mandarin is read in simplified ones.
    assert omnivoice_tts._text_for("zh", "我每天都會花時間學中文。") == "我每天都会花时间学中文。"
    # Taigi's Hanji are read in Mandarin: in POJ, like MMS.
    assert omnivoice_tts._text_for("nan", "台語") == taigi.tts_text("台語")
    assert omnivoice_tts._text_for("yue", "我好鍾意") == "我好鍾意"
    assert omnivoice_tts._text_for("fr", "Bonjour") == "Bonjour"
    assert all(omnivoice_tts.supports(key) for key in LANGUAGES) and not omnivoice_tts.supports("ar")
    assert omnivoice_tts.voice_id("nan") == "nan-OmniVoice" and omnivoice_tts.voice_language("yue-OmniVoice") == "yue"
    assert omnivoice_tts.is_voice("nan-OmniVoice") and not omnivoice_tts.is_voice("nan-TW-MmsTaigi")
    assert omnivoice_tts.voice_label("zh") == "OmniVoice - Mandarin (local)"


class FakeOmniVoiceProcess:
    """omnivoice_worker.py's side: ready, then one second of silence per request (the requests it got)."""

    def __init__(self, ready=None, fail=False):
        self.requests, self.fail, self.killed = [], fail, False
        self._lines = [omnivoice_worker.RESULT_PREFIX + json.dumps(ready or {"ready": True}) + "\n"]
        self.stdin = types.SimpleNamespace(write=self._write, flush=lambda: None)
        self.stdout = self

    def __iter__(self):
        while self._lines:
            yield self._lines.pop(0)

    def _write(self, line):
        request = json.loads(line)
        self.requests.append(request)
        if self.fail:
            answer = {"error": "RuntimeError: out of memory"}
        else:
            np.zeros(24000, dtype=np.float32).tofile(request["output"])
            answer = {"sample_rate": 24000}
        self._lines.append(omnivoice_worker.RESULT_PREFIX + json.dumps(answer) + "\n")

    def poll(self):
        return 1 if self.killed else None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 1


@pytest.fixture
def omnivoice_process(monkeypatch):
    """OmniVoice "installed", its process faked (the processes started)."""
    started = []

    real_popen = subprocess.Popen

    def popen(command, **kwargs):
        if command[0] == "ffmpeg":  # the mp3 encoding of the chapters is real
            return real_popen(command, **kwargs)
        assert command[1:] == ["-m", "miningcat.infrastructure.speech.omnivoice_worker"]
        assert command[0] == str(omnivoice_tts.PYTHON)  # its own environment's Python
        started.append(FakeOmniVoiceProcess())
        return started[-1]

    monkeypatch.setattr(omnivoice_tts, "installed", lambda: True)
    monkeypatch.setattr(omnivoice_tts.subprocess, "Popen", popen)
    monkeypatch.setattr(omnivoice_tts, "_worker", omnivoice_tts.OmniVoiceWorker())
    return started


def test_omnivoice_reads_with_the_voice_of_the_language(omnivoice_process):
    pytest.importorskip("opencc")
    samples, rate = omnivoice_tts.synthesize("時間", "zh", 16)
    assert rate == 24000 and len(samples) == 24000 and samples.dtype == np.float32
    omnivoice_tts.synthesize("Bonjour", "fr")
    assert len(omnivoice_process) == 1  # started once, kept for the next sentences
    zh, fr = omnivoice_process[0].requests
    assert (zh["text"], zh["language"], zh["num_step"], zh["seed"]) == ("时间", "zh", 16, 0)
    assert zh["voice"] == str(paths.user / "voices" / "omnivoice-zh.pt")
    assert zh["reference_text"] == omnivoice_tts.REFERENCE_TEXTS["zh"]
    assert (fr["num_step"], fr["voice"].endswith("omnivoice-fr.pt")) == (8, True)
    with pytest.raises(local_models.SpeechError, match="steps"):
        omnivoice_tts.synthesize("Bonjour", "fr", 12)
    with pytest.raises(local_models.SpeechError, match="no voice"):
        omnivoice_tts.synthesize("Hello", "ar")


def test_omnivoice_errors(omnivoice_process, monkeypatch):
    monkeypatch.setattr(omnivoice_tts.subprocess, "Popen", lambda command, **kwargs: FakeOmniVoiceProcess(fail=True))
    with pytest.raises(local_models.SpeechError, match="out of memory"):
        omnivoice_tts.synthesize("Bonjour", "fr")
    omnivoice_tts._worker.stop()
    monkeypatch.setattr(omnivoice_tts.subprocess, "Popen",
                        lambda command, **kwargs: FakeOmniVoiceProcess(ready={"error": "OSError: no space left"}))
    with pytest.raises(local_models.SpeechError, match="couldn't start: OSError: no space left"):
        omnivoice_tts.synthesize("Bonjour", "fr")
    monkeypatch.setattr(omnivoice_tts, "installed", lambda: False)
    with pytest.raises(local_models.SpeechError, match="make install-omnivoice"):
        omnivoice_tts.synthesize("Bonjour", "fr")


def test_omnivoice_chapter(omnivoice_process, tmp_path):
    path = tmp_path / "chapter.mp3"
    timed = omnivoice_tts.synthesize_chapter(["Bonjour.", "Au revoir."], "fr", path)
    assert [sentence for _, _, sentence in timed] == ["Bonjour.", "Au revoir."]
    assert timed[0][:2] == (0.0, 1.0) and timed[1][0] == pytest.approx(1.0 + omnivoice_tts.PAUSE_SECONDS)
    assert path.stat().st_size > 1000


def test_new_omnivoice_voice(omnivoice_process):
    omnivoice_tts.synthesize("Bonjour", "fr")
    voice = omnivoice_tts._voice_file("fr")
    voice.parent.mkdir(parents=True, exist_ok=True)
    voice.write_bytes(b"prompt")
    omnivoice_tts.new_voice("fr")
    assert not voice.exists() and omnivoice_process[0].killed  # the worker forgets the old voice
    omnivoice_tts.synthesize("Bonjour", "fr")
    assert omnivoice_process[1].requests[0]["seed"] == 1  # another seed, another voice
    with pytest.raises(local_models.SpeechError, match="no voice"):
        omnivoice_tts.new_voice("ar")
