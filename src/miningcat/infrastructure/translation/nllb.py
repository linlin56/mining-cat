"""Meta's NLLB-200 (No Language Left Behind), which translates the sentences and subtitles: one model for every pair
of languages, and it knows Cantonese. It runs with CTranslate2 (also used by faster-whisper), in its distilled versions
quantized to int8. Its packages are installed with `make install-nllb` (or from the settings), its models downloaded to
library/translation_models/ from Hugging Face, at a fixed revision. The weights are under CC-BY-NC 4.0: non-commercial
use only."""

import importlib
import importlib.util
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from miningcat.config.paths import paths
from miningcat.infrastructure import http
from miningcat.infrastructure.translation.errors import TranslateError

INSTALL_HINT = "make install-nllb"


@dataclass(frozen=True)
class NllbModel:
    name: str
    label: str
    repo: str
    revision: str
    size: int  # bytes, to tell the user before the download


MODELS = {
    model.name: model for model in (
        NllbModel("nllb-600m", "NLLB-200 600M", "JustFrederik/nllb-200-distilled-600M-ct2-int8",
                  "302d78f00e6fdb50a1064059df7c392b735e9d05", 630_000_000),
        NllbModel("nllb-1.3b", "NLLB-200 1.3B", "JustFrederik/nllb-200-distilled-1.3B-ct2-int8",
                  "30c36268408177b0fce2bfcfa205d877accd327d", 1_390_000_000),
    )
}
DEFAULT_MODEL = "nllb-600m"
# What CTranslate2 and the tokenizer need, the model last: a folder with it is complete.
FILES = ["config.json", "shared_vocabulary.txt", "sentencepiece.bpe.model", "model.bin"]

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


def _require(module: str):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise TranslateError(f"NLLB needs the {module} package ({exc}). Install it with `{INSTALL_HINT}`.") from exc


def model(name: str) -> NllbModel:
    if name not in MODELS:
        raise TranslateError(f"Unknown translation model: {name!r}")
    return MODELS[name]


class Nllb:
    """The NLLB-200 models: downloaded, removed, and the one loaded to translate."""

    def __init__(self):
        self._loaded: tuple[str, object, object] | None = None  # (name, translator, tokenizer)
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        """Whether its packages are installed (CTranslate2 and SentencePiece)."""
        return all(importlib.util.find_spec(m) is not None for m in ("ctranslate2", "sentencepiece"))

    @staticmethod
    def folder(name: str) -> Path:
        return paths.translation_models / name

    def installed(self, name: str) -> bool:
        """Whether the model is downloaded (not whether the packages are installed: see available)."""
        return name in MODELS and (self.folder(name) / FILES[-1]).is_file()

    def installed_models(self) -> list[dict]:
        """{"name", "label", "size"} of each downloaded model."""
        return [{"name": name, "label": m.label,
                 "size": sum(f.stat().st_size for f in self.folder(name).rglob("*") if f.is_file())}
                for name, m in MODELS.items() if self.installed(name)]

    def install(self, name: str, progress: Callable[[int, int], None] | None = None) -> None:
        """Downloads the model's files, `progress(bytes, total)` over all of them."""
        info = model(name)
        folder = self.folder(name)
        folder.mkdir(parents=True, exist_ok=True)
        done = 0
        for file in FILES:
            part = folder / f"{file}.part"
            url = f"https://huggingface.co/{info.repo}/resolve/{info.revision}/{file}"

            def on_chunk(read: int, total: int, before: int = done):
                if progress:
                    progress(before + read, max(info.size, before + total))

            try:
                http.download_to(url, part, progress=on_chunk)
            except OSError as exc:
                part.unlink(missing_ok=True)
                raise TranslateError(f"The translation model couldn't be downloaded: {exc}") from exc
            done += part.stat().st_size
            part.replace(folder / file)

    def uninstall(self, name: str) -> None:
        if not self.installed(name):
            raise TranslateError("This model isn't installed.")
        with self._lock:
            if self._loaded and self._loaded[0] == name:
                self._loaded = None
            shutil.rmtree(self.folder(name))

    def _load(self, name: str):
        if self._loaded and self._loaded[0] == name:
            return self._loaded[1:]
        if not self.installed(name):
            raise TranslateError(f"{model(name).label} isn't installed: install it in Settings › Translation, "
                                 f"or with `{INSTALL_HINT}`.")
        ctranslate2, sentencepiece = _require("ctranslate2"), _require("sentencepiece")
        folder = self.folder(name)
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        translator = ctranslate2.Translator(str(folder), device=device, compute_type="auto")
        tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(folder / "sentencepiece.bpe.model"))
        self._loaded = (name, translator, tokenizer)
        return translator, tokenizer

    def translate(self, name: str, lines: list[str], source: str, target: str) -> list[str]:
        """Lines translated from `source` to `target` (our codes, "zt" for traditional Chinese), in batches."""
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
