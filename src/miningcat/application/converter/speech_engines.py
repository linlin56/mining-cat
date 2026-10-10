"""The speech engines of a language: Whisper, or the local engines of the languages it doesn't know (Taigi). Qwen3-ASR
can also replace Whisper for the languages it knows, when one of its models is asked for (it's optional)."""
from miningcat.application.converter.errors import ConverterError
from miningcat.domain.languages import Language, SpeechEngine
from miningcat.infrastructure.speech import qwen3_asr
from miningcat.infrastructure.speech.whisper import Whisper


def _whisper(model_name: str, lang: Language) -> Whisper:
    print(f"Loading stable-whisper model '{model_name}'...")
    whisper = Whisper.load(model_name)
    whisper.ensure_supports(lang)
    return whisper


def transcriber_engine(model_name: str, lang: Language) -> SpeechEngine:
    """The engine transcribing the language: Qwen3-ASR for the languages only it knows, or when `model_name` is one of
    its models (for those languages, a Whisper size is mapped to one); else Whisper."""
    if lang.profile.transcriber is SpeechEngine.QWEN3_ASR or qwen3_asr.is_model(model_name):
        return SpeechEngine.QWEN3_ASR
    return SpeechEngine.WHISPER


def load_transcriber(model_name: str, lang: Language):
    """What transcribes the language (see transcriber_engine): a Whisper checkpoint, or Qwen3-ASR. It has a `name`
    and `transcribe(audio_file, lang)`."""
    if transcriber_engine(model_name, lang) is SpeechEngine.QWEN3_ASR:
        if not qwen3_asr.supports(lang):
            raise ConverterError(f"Qwen3-ASR doesn't transcribe {lang.profile.label}: choose a Whisper model.")
        return qwen3_asr.Qwen3Asr.load(model_name)
    return _whisper(model_name, lang)


def load_aligner(model_name: str, lang: Language):
    """What aligns a book on its audio: a Whisper checkpoint, or the MMS aligner. It has `align(audio_file, text,
    lang)`."""
    if lang.profile.aligner is SpeechEngine.MMS:
        from miningcat.infrastructure.speech.mms_aligner import MmsAligner
        return MmsAligner()
    if qwen3_asr.is_model(model_name):
        raise ConverterError("Qwen3-ASR only transcribes: a book is aligned on its audio with a Whisper model.")
    return _whisper(model_name, lang)
