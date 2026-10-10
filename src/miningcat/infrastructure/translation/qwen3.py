"""Qwen3 (Alibaba, Apache 2.0), a language model translating with context: subtitles go in numbered chunks, each with
the lines that came before and their translations, so that it knows who speaks and what is meant (omitted subjects,
pronouns, a sentence cut over several lines). Better than NLLB on spoken language, but large (8 GB) and slower: it
needs an NVIDIA GPU or an Apple Silicon Mac. It runs with transformers, the packages of Qwen3-ASR
(requirements-qwen.txt); its model is downloaded by model_files.py (see install.py)."""

import importlib.util
import re
import threading
from typing import Callable

from miningcat.infrastructure.translation import model_files
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.model_files import PinnedModel

MODELS = {
    model.name: model for model in (
        # the instruct version, without thinking
        PinnedModel("qwen3-4b", "Qwen3 4B (with context)", "Qwen/Qwen3-4B-Instruct-2507",
                    "cdbee75f17c01a7cc42f958dc650907174af0554", 8_060_000_000,
                    ("config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json", "vocab.json",
                     "merges.txt", "model.safetensors.index.json", "model-00003-of-00003.safetensors",
                     "model-00002-of-00003.safetensors", "model-00001-of-00003.safetensors")),
    )
}

# The names of our languages in the prompt ("zt": traditional Chinese).
NAMES = {
    "zh": "Chinese (simplified characters)", "zt": "Chinese (traditional characters)", "yue": "Cantonese",
    "nan": "Taiwanese Hokkien (Taigi)", "ja": "Japanese", "ko": "Korean", "vi": "Vietnamese", "en": "English",
    "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese", "pl": "Polish",
    "ru": "Russian",
}
LANGUAGES = set(NAMES) - {"zt"}

CHUNK = 16  # lines translated at once
CONTEXT = 8  # lines before them, with their translations
TOKENS_PER_LINE = 40

SYSTEM = (
    "You translate the subtitles of a video from {source} to {target}.\n"
    "You get numbered subtitle lines to translate and, before them, the lines that came just before with their "
    "translations, for context.\n"
    "Translate each numbered line on its own, in natural spoken {target}, as a subtitle: use the context to understand "
    "who speaks and what is meant (omitted subjects, pronouns, tone). A sentence may be cut over several lines: "
    "translate each part on its line. Keep names. Speaker names in parentheses, sound effects and music marks are "
    "translated briefly or kept.\n"
    "Answer with exactly one line per numbered line, with its number: `1. <translation of line 1>`, "
    "`2. <translation of line 2>`..., and nothing else."
)
_NUMBERED = re.compile(r"\s*(\d+)[.:)]\s*(.*)")


def messages(lines: list[str], context: list[tuple[str, str]], source: str, target: str) -> list[dict]:
    """The chat asking for the translation of `lines`, after `context` [(line, its translation)]."""
    parts = []
    if context:
        parts.append("Context (already translated):\n" + "\n".join(f"{s} => {t}" for s, t in context))
    parts.append("Translate:\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines)))
    return [{"role": "system", "content": SYSTEM.format(source=NAMES[source], target=NAMES[target])},
            {"role": "user", "content": "\n\n".join(parts)}]


def parse(answer: str, count: int) -> list[str] | None:
    """The translations of an answer's numbered lines, None when they aren't exactly 1 to `count`."""
    found = {}
    for line in answer.strip().splitlines():
        m = _NUMBERED.match(line)
        if m:
            found[int(m.group(1))] = m.group(2).strip()
    return [found[i] for i in range(1, count + 1)] if sorted(found) == list(range(1, count + 1)) else None


class Qwen3:
    """The Qwen3 models: downloaded, removed, and the one loaded to translate."""

    MODELS = MODELS
    LANGUAGES = LANGUAGES

    def __init__(self):
        self._loaded: tuple[str, object, object, str] | None = None  # (name, model, tokenizer, device)
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        """Whether its packages are installed (transformers, accelerate and PyTorch)."""
        return all(importlib.util.find_spec(m) is not None for m in ("transformers", "accelerate", "torch"))

    @staticmethod
    def installed(name: str) -> bool:
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
        """Frees the memory of the model loaded (several GB), when another engine translates. Not while it
        translates: nothing waits for it."""
        if self._lock.acquire(blocking=False):
            self._loaded = None
            self._lock.release()

    def _load(self, name: str):
        if self._loaded and self._loaded[0] == name:
            return self._loaded[1:]
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise TranslateError(f"Qwen3 needs the transformers package ({exc}). Install it from Settings › "
                                 "Translation.") from exc
        from miningcat.infrastructure.speech.local_models import torch_device
        device = torch_device()
        # half precision on GPUs (the model takes 8 GB, twice as much in float32)
        dtype = torch.bfloat16 if device in ("cuda", "mps") else torch.float32
        folder = model_files.folder(MODELS[name])
        print(f"Loading {MODELS[name].label} on {device}...")
        tokenizer = AutoTokenizer.from_pretrained(folder)
        model = AutoModelForCausalLM.from_pretrained(folder, dtype=dtype).to(device).eval()
        self._loaded = (name, model, tokenizer, device)
        return model, tokenizer, device

    def _generate(self, name: str, chat: list[dict], max_tokens: int) -> str:
        import torch
        model, tokenizer, device = self._load(name)
        text = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(device)
        with torch.no_grad():
            output = model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                    temperature=None, top_p=None, top_k=None)
        return tokenizer.decode(output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    def _translate_chunk(self, name: str, lines: list[str], context: list[tuple[str, str]], source: str,
                         target: str) -> list[str]:
        """A chunk translated; when the answer doesn't have one line per line, each half on its own."""
        answer = self._generate(name, messages(lines, context, source, target), TOKENS_PER_LINE * len(lines) + 20)
        translated = parse(answer, len(lines))
        if translated is not None:
            return translated
        if len(lines) == 1:
            return [answer.strip().splitlines()[0] if answer.strip() else ""]
        half = len(lines) // 2
        first = self._translate_chunk(name, lines[:half], context, source, target)
        context = (context + list(zip(lines[:half], first)))[-CONTEXT:]
        return first + self._translate_chunk(name, lines[half:], context, source, target)

    def translate_lines(self, name: str, lines: list[str], source: str, target: str,
                        progress: Callable[[int, int], None] | None = None) -> list[str]:
        """Lines translated from `source` to `target` (our codes, "zt" for traditional Chinese), in order, CHUNK at a
        time, each chunk after the CONTEXT lines before it. `progress(done, total)` after each chunk."""
        if source not in NAMES or target not in NAMES:
            raise TranslateError(f"Qwen3 can't translate from {source} to {target}.")
        translated, context = [], []
        with self._lock:
            for start in range(0, len(lines), CHUNK):
                chunk = lines[start:start + CHUNK]
                done = self._translate_chunk(name, chunk, context, source, target)
                translated += done
                context = (context + list(zip(chunk, done)))[-CONTEXT:]
                if progress:
                    progress(len(translated), len(lines))
        return translated
