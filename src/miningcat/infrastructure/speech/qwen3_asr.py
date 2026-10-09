"""Transcription with Qwen3-ASR (Alibaba, Apache 2.0), which knows Minnan among its Chinese dialects: it writes Taigi
speech in Chinese characters. It also knows the other languages of the app: it can replace Whisper for them, when it's
installed (`make install-qwen`), with its own model names (qwen3-0.6b, qwen3-1.7b). The audio is cut into utterances by a voice activity detector (Silero, shipped with
faster-whisper), each one transcribed: its subtitles take the utterance's times, shared between its sentences."""

import importlib.util
import sys
import types

from tqdm import tqdm

from miningcat.domain.languages import Language, WordSegmentation
from miningcat.domain.subtitles.segment import Segment
from miningcat.domain.text.sentences import split_sentences
from miningcat.infrastructure.speech.local_models import (
    SAMPLE_RATE,
    SpeechError,
    load_audio,
    local_model,
    require,
    torch_device,
)

MODELS = {"qwen3-0.6b": "Qwen/Qwen3-ASR-0.6B", "qwen3-1.7b": "Qwen/Qwen3-ASR-1.7B"}
DEFAULT_MODEL = "qwen3-0.6b"
# The CLI's Whisper sizes, for a language transcribed by Qwen3-ASR: the large ones get the large model.
_FROM_WHISPER_SIZE = {"medium": "qwen3-1.7b", "large": "qwen3-1.7b", "turbo": "qwen3-1.7b"}
# Qwen3-ASR's language for ours (Minnan is one of its Chinese dialects). No context: it's written out as is on
# music and silences ("臺語（閩南語）。").
QWEN_LANGUAGES = {
    "zh": "Chinese", "yue": "Cantonese", "nan": "Chinese", "ja": "Japanese", "ko": "Korean", "vi": "Vietnamese",
    "en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "pl": "Polish",
}

MAX_UTTERANCE_SECONDS = 20
# Speech probability above which the voice activity detector hears speech. Its default (0.5) misses the lines shouted
# or spoken over music (anime, films): lower, they're kept, still without the songs and the silences.
VAD_THRESHOLD = 0.2
BATCH_SIZE = 8


def model_name(name: str | None) -> str:
    """A Qwen3-ASR model for a model name given to the CLI (qwen3-1.7b, or a Whisper size)."""
    name = (name or "").lower()
    return name if name in MODELS else _FROM_WHISPER_SIZE.get(name, DEFAULT_MODEL)


def _import_qwen_asr():
    # qwen_asr imports nagisa (a Japanese tokenizer, for its forced aligner, which isn't used here) when it's
    # loaded: nagisa doesn't build on recent Pythons, a placeholder module lets the transcriber load without it.
    try:
        import nagisa  # noqa: F401
    except ImportError:
        sys.modules["nagisa"] = types.ModuleType("nagisa")
    return require("qwen_asr", "Transcription with Qwen3-ASR")


def load_model(name: str | None = None):
    qwen_asr = _import_qwen_asr()
    torch = require("torch", "Transcription with Qwen3-ASR")
    device = torch_device()
    # bfloat16 on NVIDIA GPUs; float32 elsewhere (half precision is slow on CPUs and unreliable on Apple's GPUs)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    repo = MODELS[model_name(name)]
    print(f"Loading Qwen3-ASR ({repo}) on {device}...")
    return qwen_asr.Qwen3ASRModel.from_pretrained(
        local_model(repo), dtype=dtype, device_map=device, max_inference_batch_size=BATCH_SIZE, max_new_tokens=256,
    )


def utterances(samples, max_seconds: float = MAX_UTTERANCE_SECONDS) -> list[tuple[int, int]]:
    """(start, end) sample positions of the speech of the audio, no longer than max_seconds each."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(threshold=VAD_THRESHOLD, min_silence_duration_ms=300, max_speech_duration_s=max_seconds,
                         speech_pad_ms=200)
    return [(chunk["start"], chunk["end"]) for chunk in get_speech_timestamps(samples, options, sampling_rate=SAMPLE_RATE)]


def is_model(name: str | None) -> bool:
    """Whether a model name given to the CLI is Qwen3-ASR's (rather than a Whisper size)."""
    return (name or "").lower() in MODELS


def supports(lang: Language) -> bool:
    return lang.profile.key in QWEN_LANGUAGES


def installed() -> bool:
    """Whether qwen-asr is installed (`make install-qwen`): it's optional, its models and packages are large."""
    importlib.invalidate_caches()  # it may have been installed while the server runs
    return importlib.util.find_spec("qwen_asr") is not None


def max_subtitle_chars(lang: Language) -> int:
    """The length of a subtitle cut from an utterance: a line of characters, or of words separated by spaces."""
    return 80 if lang.profile.word_segmentation is WordSegmentation.SPACES else 30


def _split_times(text: str, start: float, end: float, max_chars: int = 30) -> list[tuple[float, float, str]]:
    """The text of an utterance cut into sentences (the commas of a long one), its time shared between them."""
    pieces = split_sentences(text, max_chars)
    total = sum(len(p) for p in pieces) or 1
    timed, position = [], start
    for piece in pieces:
        length = (end - start) * len(piece) / total
        timed.append((position, position + length, piece))
        position += length
    return timed


def transcribe(model, audio_file, language: str = "nan", progress: bool = True, max_chars: int = 30) -> list:
    """Subtitles of an audio file."""
    samples = load_audio(audio_file)
    spans = utterances(samples)
    if not spans:
        return []
    segments = []
    batches = range(0, len(spans), BATCH_SIZE)
    for first in tqdm(batches, desc="Transcription", unit="batch", disable=not progress):
        batch = spans[first:first + BATCH_SIZE]
        try:
            results = model.transcribe(
                audio=[(samples[s:e], SAMPLE_RATE) for s, e in batch],
                language=QWEN_LANGUAGES.get(language),
            )
        except Exception as exc:  # out of memory, a model that couldn't be downloaded...
            raise SpeechError(f"Qwen3-ASR couldn't transcribe the audio: {exc}") from exc
        for (s, e), result in zip(batch, results):
            text = (result.text or "").strip()
            for start, end, piece in _split_times(text, s / SAMPLE_RATE, e / SAMPLE_RATE, max_chars) if text else ():
                segments.append(Segment(0, round(start, 3), round(end, 3), piece))
    return segments


class Qwen3Asr:
    """Qwen3-ASR, as the converter uses a transcription model (like infrastructure/speech/whisper.py's Whisper)."""

    name = "Qwen3-ASR"

    def __init__(self, model):
        self._model = model

    @classmethod
    def load(cls, model_name: str | None = None) -> "Qwen3Asr":
        return cls(load_model(model_name))

    def transcribe(self, audio_file, lang: Language) -> list[Segment]:
        return transcribe(self._model, audio_file, language=lang.profile.key, max_chars=max_subtitle_chars(lang))
