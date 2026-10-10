import re
import threading
from typing import Callable

from miningcat.application.anki.config import get_config
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.subtitles.srt import replace_srt_lines, srt_lines
from miningcat.domain.text.chinese_script import chinese_script
from miningcat.infrastructure.translation import nllb_install
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.nllb import DEFAULT_MODEL, LANGUAGES as NLLB_LANGUAGES, MODELS, Nllb

DEFAULT_TARGET = "en"
MAX_CHARS = 1000
# Subtitles are translated a few lines at a time (faster than one by one), the progress shown after each.
LINES_PER_STEP = 32

nllb = Nllb()
# One install at a time.
_lock = threading.Lock()


def model() -> str:
    """The NLLB-200 model of the settings."""
    chosen = get_config().get("translation_model", DEFAULT_MODEL)
    return chosen if chosen in MODELS else DEFAULT_MODEL


def translatable(language: str) -> bool:
    return language in NLLB_LANGUAGES


def targets() -> list[dict]:
    """The languages sentences can be translated to."""
    return [{"id": key, "name": LANGUAGES[key]} for key in LANGUAGES if translatable(key)]


def target_language() -> str:
    """The language sentences are translated to ("" when they aren't), from the settings."""
    target = get_config().get("translation_language", DEFAULT_TARGET)
    return target if target == "" or translatable(target) else DEFAULT_TARGET


def _code(language: str, text: str = "") -> str:
    """NLLB has a code for traditional Chinese ("zt") besides simplified ("zh")."""
    if language == "zh" and text and chinese_script(text) == "traditional":
        return "zt"
    return language


def installed(name: str) -> bool:
    """Whether the model can translate: the packages are there, and the model downloaded."""
    return nllb.available() and nllb.installed(name)


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
                if not nllb.available():
                    self.state.update(step="packages")
                    if nllb_install.install_packages() != 0:
                        raise TranslateError("The packages couldn't be installed: see pip's output in the terminal.")
                self.state.update(step="model")
                nllb.install(name, progress=lambda done, total: self.state.update(done=done, total=total))
            self.state.update(state="done")
        except Exception as exc:
            self.state.update(state="error", error=str(exc))


_install = ModelInstall()


def models() -> dict:
    """The models (whether each is downloaded, its size), the one of the settings, and the install in progress."""
    sizes = {m["name"]: m["size"] for m in nllb.installed_models()}
    return {
        "model": model(),
        "available": nllb.available(),
        "models": [{"id": name, "label": m.label, "installed": installed(name), "size": sizes.get(name, m.size)}
                   for name, m in MODELS.items()],
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
        nllb.uninstall(name)


def _translate(lines: list[str], source: str, target: str) -> list[str]:
    """Lines translated by the model of the settings, which must be downloaded (it's never downloaded here)."""
    name = model()
    if not installed(name):
        raise TranslateError(f"{MODELS[name].label} isn't downloaded yet: download it in Settings › Translation, "
                             f"or with `{nllb_install.MAKE_TARGET}`.")
    try:
        return [re.sub(r"\s+", " ", line).strip() for line in nllb.translate(name, lines, source, target)]
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
    """The text translated to the language of the settings, or None when there's nothing to do."""
    target = target_language()
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or not target or target == language:
        return None
    if not translatable(language):
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if len(text) > MAX_CHARS:
        raise TranslateError(f"Sentences are limited to {MAX_CHARS} characters.")
    return _translate([text], _code(language, text), _code(target))[0]


def translate_lines(language: str, lines: list[str],
                    progress: Callable[[int, int], None] | None = None) -> list[str]:
    """Lines (of subtitles) translated to the language of the settings, a few at a time. `progress(done, total)` after
    each step."""
    target = check(language)
    # The script of the whole text tells traditional from simplified Chinese better than a short line's.
    source, target = _code(language, "".join(lines)), _code(target)
    translated = []
    for start in range(0, len(lines), LINES_PER_STEP):
        translated += _translate(lines[start:start + LINES_PER_STEP], source, target)
        if progress:
            progress(len(translated), len(lines))
    return translated


def translate_srt(language: str, srt: str, progress: Callable[[int, int], None] | None = None) -> str:
    """SRT subtitles translated to the language of the settings, line by line: the same numbers, timestamps and
    formatting."""
    lines = srt_lines(srt)
    if not lines:
        raise TranslateError("These subtitles have no text to translate.")
    return replace_srt_lines(srt, dict(zip(lines, translate_lines(language, lines, progress))))
