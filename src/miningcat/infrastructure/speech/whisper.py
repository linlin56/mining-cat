from pathlib import Path

from miningcat.domain.languages import Language
from miningcat.domain.subtitles.segment import Segment


def device() -> str:
    """The device Whisper runs on: the GPU when PyTorch has CUDA."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def segments_of(result) -> list[Segment]:
    """The non-empty segments of a stable-whisper result (an object, or a dict)."""
    raw_segs = result.segments if hasattr(result, "segments") else result.get("segments", [])
    segs = []
    for seg in raw_segs:
        start = seg.start if hasattr(seg, "start") else seg["start"]
        end = seg.end if hasattr(seg, "end") else seg["end"]
        text = (seg.text if hasattr(seg, "text") else seg["text"]).strip()
        if text:
            segs.append(Segment(0, start, end, text))
    return segs


class Whisper:
    """A stable-whisper model: forced alignment of a text on its audio, and free transcription."""

    name = "Whisper"

    def __init__(self, model):
        self._model = model

    @classmethod
    def load(cls, model_name: str) -> "Whisper":
        import stable_whisper

        return cls(stable_whisper.load_model(model_name, device=device()))

    def ensure_supports(self, lang: Language) -> None:
        """Some languages (like Cantonese) are only known to the large-v3 and turbo checkpoints."""
        from whisper.tokenizer import LANGUAGES

        code = lang.profile.whisper_code
        if code not in tuple(LANGUAGES.keys())[:self._model.num_languages]:
            raise ValueError(
                f"This Whisper checkpoint only supports {self._model.num_languages} languages and "
                f"doesn't include {lang.name} (code '{code}'). Use --model large (large-v3) "
                f"or turbo instead."
            )

    def align(self, audio_file: Path, text: str, lang: Language) -> list[Segment]:
        result = self._model.align(str(audio_file), text, language=lang.profile.whisper_code, verbose=False)
        return segments_of(result)

    def transcribe(self, audio_file: Path, lang: Language) -> list[Segment]:
        result = self._model.transcribe(str(audio_file), language=lang.profile.whisper_code, verbose=False)
        return segments_of(result)
