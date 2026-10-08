"""The speech engines of a language: Whisper, or the local engines of the languages it doesn't know (Taigi)."""
from miningcat.domain.languages import Language, SpeechEngine
from miningcat.infrastructure.speech.whisper import Whisper


def _whisper(model_name: str, lang: Language) -> Whisper:
    print(f"Loading stable-whisper model '{model_name}'...")
    whisper = Whisper.load(model_name)
    whisper.ensure_supports(lang)
    return whisper


def load_transcriber(model_name: str, lang: Language):
    """What transcribes the language: a Whisper checkpoint, or Qwen3-ASR (`model_name` is then Qwen3-ASR's size, or a
    Whisper size mapped to one). It has a `name` and `transcribe(audio_file, lang)`."""
    if lang.profile.transcriber is SpeechEngine.QWEN3_ASR:
        from miningcat.infrastructure.speech.qwen3_asr import Qwen3Asr
        return Qwen3Asr.load(model_name)
    return _whisper(model_name, lang)


def load_aligner(model_name: str, lang: Language):
    """What aligns a book on its audio: a Whisper checkpoint, or the MMS aligner. It has `align(audio_file, text,
    lang)`."""
    if lang.profile.aligner is SpeechEngine.MMS:
        from miningcat.infrastructure.speech.mms_aligner import MmsAligner
        return MmsAligner()
    return _whisper(model_name, lang)
