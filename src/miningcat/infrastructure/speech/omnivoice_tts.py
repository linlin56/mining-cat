"""Text-to-speech with OmniVoice (k2-fsa/OmniVoice: code Apache 2.0, model CC BY-NC 4.0, non-commercial use only), the
local voice of every language. Edge's voices are faster, but online: they're used instead when the settings say so,
and OmniVoice takes over when Edge fails.

OmniVoice needs transformers 5, while Qwen3-ASR pins 4.57.6: it's installed in its own environment, .venv-omnivoice
(`make install-omnivoice`), and runs in its own process (omnivoice_worker.py), started on the first sentence read and
kept for the next ones. Its model (2.4 GB) is downloaded from Hugging Face the first time.

Each language has its own voice: OmniVoice makes one up the first time the language is read, and it's kept in
user/voices/ so that every sentence is read by the same voice. `new_voice` makes up another one."""

import json
import platform
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np

from miningcat.config.paths import PROJECT_ROOT, paths
from miningcat.config.runtime import SRC_DIR
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.text import taigi
from miningcat.domain.text.script_conversion import ConversionError, convert_text
from miningcat.infrastructure.speech.local_models import SpeechError, encode_mp3
from miningcat.infrastructure.speech.omnivoice_worker import RESULT_PREFIX

VENV = PROJECT_ROOT / ".venv-omnivoice"
PYTHON = VENV / "Scripts" / "python.exe" if platform.system() == "Windows" else VENV / "bin" / "python3"
INSTALL_COMMAND = "make install-omnivoice"

# Diffusion steps: 8 is fast and good enough, 16 and 32 a little clearer (and two and four times slower).
STEPS = (8, 16, 32)
DEFAULT_STEPS = 8
PAUSE_SECONDS = 0.3  # silence between two sentences of a chapter

# The sentence OmniVoice reads when it makes up the voice of a language. Mandarin in simplified characters: read in
# traditional ones, OmniVoice mixes in Cantonese readings (see _text_for).
REFERENCE_TEXTS = {
    "de": "Ich lerne jeden Tag ein bisschen Deutsch.",
    "en": "I've been learning a new language every evening.",
    "es": "Me gusta mucho pasear por la ciudad al atardecer.",
    "fr": "J'apprends une nouvelle langue tous les soirs.",
    "it": "Ogni mattina prendo un caffè al bar sotto casa.",
    "ja": "毎朝、駅まで歩いて行きます。",
    "ko": "저는 매일 한국어를 조금씩 공부해요.",
    "pl": "Codziennie rano piję kawę i czytam gazetę.",
    "pt": "Eu gosto muito de caminhar na praia no fim de semana.",
    "ru": "Я каждый день читаю немного по-русски.",
    "vi": "Tôi học tiếng Việt mỗi ngày một chút.",
    "zh": "我每天晚上都会花一点时间学中文。",
    "yue": "我好鍾意喺海邊散步。",
    "nan": "我逐工攏會學一屑仔台語。",
}


VOICE_SUFFIX = "-OmniVoice"


def voice_id(language: str) -> str:
    """The id of OmniVoice's voice of a study language: "zh-OmniVoice". Like Edge's, it starts with the language."""
    return language + VOICE_SUFFIX


def voice_label(language: str) -> str:
    return f"OmniVoice - {LANGUAGES.get(language, language)} (local)"


def is_voice(voice: str) -> bool:
    """Whether a voice id is OmniVoice's."""
    return voice.endswith(VOICE_SUFFIX)


def voice_language(voice: str) -> str:
    """The study language of one of OmniVoice's voices: "zh-OmniVoice" -> "zh"."""
    return voice[:-len(VOICE_SUFFIX)]


def installed() -> bool:
    """Whether .venv-omnivoice holds OmniVoice."""
    return PYTHON.exists() and any(VENV.glob("**/site-packages/omnivoice/__init__.py"))


def supports(language: str) -> bool:
    """Whether OmniVoice reads a study language ("zh", "ja"...)."""
    return language in REFERENCE_TEXTS


def _text_for(language: str, text: str) -> str:
    """The text as OmniVoice reads it best. Mandarin in simplified characters: in traditional ones, it reads some of
    them in Cantonese (時間 as "si gaan"). Taigi in POJ: it barely knows Taigi's Hanji (17 hours of training data),
    and reads them in Mandarin (台語 as "táiyǔ" instead of "Tâi-gí")."""
    if language == "zh":
        try:
            return convert_text(text, "tw", "s")
        except ConversionError:  # no OpenCC: read as it is
            return text
    if language == "nan":
        return taigi.tts_text(text)
    return text


# The voice of a language: its file, and the seed it was made up with (another seed, another voice).
def _voice_file(language: str) -> Path:
    return paths.user / "voices" / f"omnivoice-{language}.pt"


def _seeds_file() -> Path:
    return paths.user / "voices" / "omnivoice-seeds.json"


def _seeds() -> dict:
    try:
        return json.loads(_seeds_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _seed(language: str) -> int:
    return int(_seeds().get(language, 0))


class OmniVoiceWorker:
    """The OmniVoice process (see omnivoice_worker.py), started on the first sentence and kept for the next ones
    (loading the model takes a while). One sentence at a time: it's restarted when it died."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        with self._lock:
            self._ensure()

    def read(self, request: dict) -> tuple[np.ndarray, int]:
        """(mono float32 samples, sample rate) of a request (see omnivoice_worker.py), its "output" left out."""
        with self._lock:
            with tempfile.TemporaryDirectory(prefix="miningcat-omnivoice-") as folder:
                output = Path(folder) / "samples.f32"
                for attempt in range(2):
                    proc = self._ensure()
                    try:
                        proc.stdin.write(json.dumps({**request, "output": str(output)}, ensure_ascii=False) + "\n")
                        proc.stdin.flush()
                        answer = self._answer(proc)
                    except (OSError, SpeechError):
                        self.stop()
                        if attempt:
                            raise SpeechError("OmniVoice stopped unexpectedly.")
                        continue
                    if "error" in answer:
                        raise SpeechError(f"OmniVoice couldn't read the sentence: {answer['error']}")
                    return np.fromfile(output, dtype=np.float32), int(answer["sample_rate"])
        raise SpeechError("OmniVoice stopped unexpectedly.")

    def _ensure(self) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self.stop()
        if not installed():
            raise SpeechError(f"The local voice needs OmniVoice: install it with `{INSTALL_COMMAND}`.")
        self._proc = subprocess.Popen(
            [str(PYTHON), "-m", "miningcat.infrastructure.speech.omnivoice_worker"], cwd=str(SRC_DIR),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        try:
            answer = self._answer(self._proc)  # {"ready": true}, once the model is loaded
        except SpeechError:
            self.stop()
            raise SpeechError("OmniVoice couldn't start.")
        if "error" in answer:
            self.stop()
            raise SpeechError(f"OmniVoice couldn't start: {answer['error']}")
        return self._proc

    @staticmethod
    def _answer(proc: subprocess.Popen) -> dict:
        for line in proc.stdout:
            if line.startswith(RESULT_PREFIX):
                return json.loads(line[len(RESULT_PREFIX):])
        raise SpeechError("OmniVoice stopped unexpectedly.")

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._proc = None


_worker = OmniVoiceWorker()


def preload() -> None:
    """Starts OmniVoice in the background (loading the model takes a while), so that the first sentence is read
    sooner."""
    if installed():
        threading.Thread(target=_preload, daemon=True).start()


def _preload() -> None:
    try:
        _worker.start()
    except SpeechError:  # reported when a sentence is read
        pass


def synthesize(text: str, language: str, steps: int = DEFAULT_STEPS) -> tuple[np.ndarray, int]:
    """(mono float32 samples, sample rate) of the text read by the voice of the language."""
    if not supports(language):
        raise SpeechError(f"OmniVoice has no voice for this language ({language}).")
    if steps not in STEPS:
        raise SpeechError(f"Unsupported number of steps: {steps} (supported: {', '.join(map(str, STEPS))}).")
    return _worker.read({
        "text": _text_for(language, text),
        "language": language,
        "num_step": steps,
        "voice": str(_voice_file(language)),
        "reference_text": _text_for(language, REFERENCE_TEXTS[language]),
        "seed": _seed(language),
    })


def synthesize_mp3(text: str, language: str, steps: int = DEFAULT_STEPS) -> bytes:
    samples, rate = synthesize(text, language, steps)
    if not len(samples):
        raise SpeechError("There's nothing the voice can read in this text.")
    return encode_mp3(samples, rate)


def synthesize_chapter(sentences: list[str], language: str, audio_path, steps: int = DEFAULT_STEPS) -> list[tuple[float, float, str]]:
    """Reads the sentences one after the other into an MP3 file. Returns the (start, end, sentence) of each."""
    pieces, timed, position, rate = [], [], 0.0, 24000
    for sentence in sentences:
        samples, rate = synthesize(sentence, language, steps)
        if not len(samples):
            if timed:  # punctuation, numbers: shown with the sentence before
                timed[-1] = (*timed[-1][:2], timed[-1][2] + sentence)
            continue
        duration = len(samples) / rate
        timed.append((position, position + duration, sentence))
        pieces += [samples, np.zeros(int(PAUSE_SECONDS * rate), dtype=np.float32)]
        position += duration + PAUSE_SECONDS
    if not pieces:
        raise SpeechError("There's nothing the voice can read in this text.")
    encode_mp3(np.concatenate(pieces), rate, audio_path)
    return timed


def new_voice(language: str) -> None:
    """Makes OmniVoice make up another voice for the language, the next time it's read."""
    if not supports(language):
        raise SpeechError(f"OmniVoice has no voice for this language ({language}).")
    seeds = _seeds()
    seeds[language] = int(seeds.get(language, 0)) + 1
    _seeds_file().parent.mkdir(parents=True, exist_ok=True)
    _seeds_file().write_text(json.dumps(seeds, indent=2), encoding="utf-8")
    _voice_file(language).unlink(missing_ok=True)
    _worker.stop()  # the running worker keeps the old voice in memory
