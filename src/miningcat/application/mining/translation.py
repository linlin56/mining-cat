import re
import threading
from typing import Callable

from miningcat.application.anki.config import get_config
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.subtitles.srt import replace_srt_lines, srt_lines
from miningcat.domain.text.chinese_script import chinese_script
from miningcat.infrastructure.translation import install as model_install
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.install import DEFAULT_MODEL, MODELS
from miningcat.infrastructure.translation.nllb import Nllb
from miningcat.infrastructure.translation.qwen3 import Qwen3

DEFAULT_TARGET = "en"
MAX_CHARS = 1000

# The engines: NLLB-200 (a line at a time, fast) and Qwen3 (with context, better, large). One model is loaded at a time.
nllb = Nllb()
qwen = Qwen3()
# One install at a time.
_lock = threading.Lock()


def model() -> str:
    """The translation model of the settings."""
    chosen = get_config().get("translation_model", DEFAULT_MODEL)
    return chosen if chosen in MODELS else DEFAULT_MODEL


def model_label() -> str:
    """The name of the translation model of the settings, shown where it translates ("Qwen3 4B")."""
    return MODELS[model()].label


def _engine(name: str):
    return nllb if name in nllb.MODELS else qwen


def card_model() -> str:
    """The model translating the cards' sentences: NLLB-200, fast, even when Qwen3 translates the subtitles (it takes
    a second or two per sentence, and 8 GB of memory), unless the settings ask for it (translation_cards_with_context).
    The NLLB model then is the larger one downloaded."""
    name = model()
    if _engine(name) is nllb or get_config().get("translation_cards_with_context"):
        return name
    return next((n for n in ("nllb-1.3b", "nllb-600m") if installed(n)), DEFAULT_MODEL)


def translatable(language: str) -> bool:
    """Whether the model of the settings translates the language."""
    return language in _engine(model()).LANGUAGES


def targets() -> list[dict]:
    """The languages sentences can be translated to."""
    return [{"id": key, "name": LANGUAGES[key]} for key in LANGUAGES if translatable(key)]


def target_language() -> str:
    """The language sentences are translated to ("" when they aren't), from the settings."""
    target = get_config().get("translation_language", DEFAULT_TARGET)
    return target if target == "" or translatable(target) else DEFAULT_TARGET


def _code(language: str, text: str = "") -> str:
    """Our code for traditional Chinese ("zt"), for the engines, besides simplified ("zh")."""
    if language == "zh" and text and chinese_script(text) == "traditional":
        return "zt"
    return language


def installed(name: str) -> bool:
    """Whether the model can translate: the packages of its engine are there, and the model downloaded."""
    engine = _engine(name)
    return engine.available() and engine.installed(name)


class ModelInstall:
    """The install of a model, in the background: the packages first when they're missing, then the model."""

    def __init__(self):
        self.state = {"state": "idle", "model": "", "step": "", "done": 0, "total": 0, "error": None}

    @property
    def running(self) -> bool:
        return self.state["state"] == "running"

    def start(self, name: str) -> None:
        self.state.update(state="running", model=name, step="", done=0, total=0, error=None)
        threading.Thread(target=self._run, args=(name,), daemon=True, name="miningcat-translation-model").start()

    def _run(self, name: str) -> None:
        try:
            with _lock:
                engine = _engine(name)
                if not engine.available():
                    self.state.update(step="packages")
                    if model_install.install_packages(name) != 0:
                        raise TranslateError("The packages couldn't be installed: see pip's output in the terminal.")
                self.state.update(step="model")
                engine.install(name, progress=lambda done, total: self.state.update(done=done, total=total))
            self.state.update(state="done")
        except Exception as exc:
            self.state.update(state="error", error=str(exc))


_install = ModelInstall()


def models() -> dict:
    """The models (whether each is downloaded, its size), the one of the settings, and the install in progress."""
    return {
        "model": model(),
        "card_model": card_model(),
        "cards_with_context": bool(get_config().get("translation_cards_with_context")),
        "models": [{"id": name, "label": m.label, "installed": installed(name), "size": m.size,
                    "context": _engine(name) is qwen} for name, m in MODELS.items()],
        "job": dict(_install.state),
    }


def start_install(name: str) -> None:
    """Installs a model, in the background (the packages first when they're missing)."""
    if name not in MODELS:
        raise TranslateError(f"Unknown translation model: {name!r}")
    if _install.running:
        raise TranslateError("A model is already being downloaded.")
    if installed(name):
        raise TranslateError(f"{MODELS[name].label} is already downloaded.")
    _install.start(name)


def delete_model(name: str) -> None:
    """Removes a model (the packages stay)."""
    if name not in MODELS:
        raise TranslateError(f"Unknown translation model: {name!r}")
    with _lock:
        _engine(name).uninstall(name)


def _translate(name: str, lines: list[str], source: str, target: str,
               progress: Callable[[int, int], None] | None = None) -> list[str]:
    """Lines translated by a model, which must be downloaded (it's never downloaded here)."""
    if not installed(name):
        raise TranslateError(f"{MODELS[name].label} isn't downloaded yet: download it in Settings › Translation, "
                             f"or with `{model_install.MAKE_TARGET}`.")
    engine = _engine(name)
    # the memory of an engine the settings don't use anymore
    used = {_engine(model()), _engine(card_model())}
    for other in (nllb, qwen):
        if other not in used:
            other.unload()
    try:
        return [re.sub(r"\s+", " ", line).strip() for line in engine.translate_lines(name, lines, source, target, progress)]
    except TranslateError:
        raise
    except Exception as exc:
        raise TranslateError(f"The text couldn't be translated: {exc}")


def check(language: str) -> str:
    """The language of the settings, when a text in `language` can be translated to it; raises TranslateError."""
    target = target_language()
    if not target:
        raise TranslateError("Choose the language sentences are translated to in the settings first.")
    if target == language:
        raise TranslateError(f"These subtitles are already in {LANGUAGES[target]}.")
    if not translatable(language):
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    return target


def translate(language: str, text: str) -> str | None:
    """A card's sentence translated to the language of the settings (by card_model()), or None when there's nothing to
    do."""
    target = target_language()
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or not target or target == language:
        return None
    name = card_model()
    if language not in _engine(name).LANGUAGES or target not in _engine(name).LANGUAGES:
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if len(text) > MAX_CHARS:
        raise TranslateError(f"Sentences are limited to {MAX_CHARS} characters.")
    return _translate(name, [text], _code(language, text), _code(target))[0]


def translate_lines(language: str, lines: list[str],
                    progress: Callable[[int, int], None] | None = None) -> list[str]:
    """Lines (of subtitles, in order) translated to the language of the settings, a few at a time (Qwen3 with the
    lines before them as context). `progress(done, total)` after each step."""
    target = check(language)
    # The script of the whole text tells traditional from simplified Chinese better than a short line's.
    return _translate(model(), lines, _code(language, "".join(lines)), _code(target), progress)


def translate_srt(language: str, srt: str, progress: Callable[[int, int], None] | None = None) -> str:
    """SRT subtitles translated to the language of the settings, line by line: the same numbers, timestamps and
    formatting."""
    lines = srt_lines(srt)
    if not lines:
        raise TranslateError("These subtitles have no text to translate.")
    return replace_srt_lines(srt, dict(zip(lines, translate_lines(language, lines, progress))))
