"""Meta's NLLB-200 (No Language Left Behind): one model for every pair of languages, and it knows Cantonese. It translates
a line at a time, fast. It runs with CTranslate2 (also used by faster-whisper), in its distilled versions quantized to
int8. Its packages are installed with requirements-nllb.txt, its models downloaded by model_files.py (see install.py).
The weights are under CC-BY-NC 4.0: non-commercial use only."""

import importlib
import importlib.util
import threading
from typing import Callable

from miningcat.infrastructure.translation import model_files
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.model_files import PinnedModel

# What CTranslate2 and the tokenizer need, the model last.
_FILES = ("config.json", "shared_vocabulary.txt", "sentencepiece.bpe.model", "model.bin")
MODELS = {
    model.name: model for model in (
        PinnedModel("nllb-600m", "NLLB-200 600M", "JustFrederik/nllb-200-distilled-600M-ct2-int8",
                    "302d78f00e6fdb50a1064059df7c392b735e9d05", 630_000_000, _FILES),
        PinnedModel("nllb-1.3b", "NLLB-200 1.3B", "JustFrederik/nllb-200-distilled-1.3B-ct2-int8",
                    "30c36268408177b0fce2bfcfa205d877accd327d", 1_390_000_000, _FILES),
    )
}

# NLLB's codes (FLORES-200) of our languages. "zt" is traditional Chinese. Taigi has none.
CODES = {
    "zh": "zho_Hans", "zt": "zho_Hant", "yue": "yue_Hant", "ja": "jpn_Jpan", "ko": "kor_Hang", "vi": "vie_Latn",
    "en": "eng_Latn", "fr": "fra_Latn", "de": "deu_Latn", "es": "spa_Latn", "it": "ita_Latn", "pt": "por_Latn",
    "pl": "pol_Latn", "ru": "rus_Cyrl",
}
LANGUAGES = set(CODES) - {"zt"}

BATCH_SIZE = 16
BEAM_SIZE = 4
MAX_TOKENS = 256
# Subtitles are translated a few lines at a time, the progress shown after each step.
LINES_PER_STEP = 32


def _require(module: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise TranslateError(f"NLLB needs the {module} package ({exc}). Install it from Settings › Translation.") from exc


class Nllb:
    """The NLLB-200 models: downloaded, removed, and the one loaded to translate."""

    MODELS = MODELS
    LANGUAGES = LANGUAGES

    def __init__(self):
        self._loaded: tuple[str, object, object] | None = None  # (name, translator, tokenizer)
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        """Whether its packages are installed (CTranslate2 and SentencePiece)."""
        return all(importlib.util.find_spec(m) is not None for m in ("ctranslate2", "sentencepiece"))

    @staticmethod
    def installed(name: str) -> bool:
        """Whether the model is downloaded (not whether the packages are installed: see available)."""
        return name in MODELS and model_files.downloaded(MODELS[name])

    @staticmethod
    def install(name: str, progress: Callable[[int, int], None] | None = None) -> None:
        model_files.download(MODELS[name], progress)

    def uninstall(self, name: str) -> None:
        with self._lock:
            if self._loaded and self._loaded[0] == name:
                self._loaded = None
            model_files.remove(MODELS[name])

    def unload(self) -> None:
        """Frees the memory of the model loaded, when another engine translates. Not while it
        translates: nothing waits for it."""
        if self._lock.acquire(blocking=False):
            self._loaded = None
            self._lock.release()

    def _load(self, name: str):
        if self._loaded and self._loaded[0] == name:
            return self._loaded[1:]
        ctranslate2, sentencepiece = _require("ctranslate2"), _require("sentencepiece")
        folder = model_files.folder(MODELS[name])
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        translator = ctranslate2.Translator(str(folder), device=device, compute_type="auto")
        tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(folder / "sentencepiece.bpe.model"))
        self._loaded = (name, translator, tokenizer)
        return translator, tokenizer

    def translate(self, name: str, lines: list[str], source: str, target: str) -> list[str]:
        """Lines translated from `source` to `target` (our codes, "zt" for traditional Chinese), each on its own."""
        if source not in CODES or target not in CODES:
            raise TranslateError(f"NLLB can't translate from {source} to {target}.")
        with self._lock:
            translator, tokenizer = self._load(name)
            tokens = [[CODES[source], *tokenizer.encode(line, out_type=str), "</s>"] for line in lines]
            results = translator.translate_batch(
                tokens, target_prefix=[[CODES[target]]] * len(tokens), max_batch_size=BATCH_SIZE,
                beam_size=BEAM_SIZE, max_decoding_length=MAX_TOKENS,
            )
        # each hypothesis starts with the target language's code
        return [tokenizer.decode(result.hypotheses[0][1:]) for result in results]

    def translate_lines(self, name: str, lines: list[str], source: str, target: str,
                        progress: Callable[[int, int], None] | None = None) -> list[str]:
        """The lines of subtitles translated, LINES_PER_STEP at a time, `progress(done, total)` after each step."""
        translated = []
        for start in range(0, len(lines), LINES_PER_STEP):
            translated += self.translate(name, lines[start:start + LINES_PER_STEP], source, target)
            if progress:
                progress(len(translated), len(lines))
        return translated
