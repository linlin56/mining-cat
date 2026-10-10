import re
import threading
from typing import Callable

from miningcat.application.anki.config import get_config
from miningcat.application.mining.preferences import chinese_script_preference
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.subtitles.srt import replace_srt_lines, srt_lines
from miningcat.domain.text.chinese_script import chinese_script
from miningcat.infrastructure.translation import nllb_install
from miningcat.infrastructure.translation.argos import LANGUAGES as ARGOS_LANGUAGES
from miningcat.infrastructure.translation.argos import ArgosTranslate
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.nllb import LANGUAGES as NLLB_LANGUAGES
from miningcat.infrastructure.translation.nllb import MODELS as NLLB_MODELS
from miningcat.infrastructure.translation.nllb import Nllb

DEFAULT_TARGET = "en"
MAX_CHARS = 1000
# Subtitles are translated by NLLB a few lines at a time (faster than one by one), the progress shown after each.
NLLB_LINES_PER_STEP = 32
# The engines translating the sentences (Settings › Translation): Argos Translate, or one of NLLB-200's models (optional,
# better, larger).
ARGOS = "argos"
ENGINES = {ARGOS: "Argos Translate", **{name: model.label for name, model in NLLB_MODELS.items()}}

argos = ArgosTranslate()
nllb = Nllb()
# One download and one model load at a time.
_lock = threading.Lock()


def engine() -> str:
    """The engine of the settings."""
    chosen = get_config().get("translation_engine", ARGOS)
    return chosen if chosen in ENGINES else ARGOS


def _languages(name: str) -> set[str]:
    return ARGOS_LANGUAGES if name == ARGOS else NLLB_LANGUAGES


def translatable(language: str) -> bool:
    """Whether the engine of the settings translates the language."""
    return language in _languages(engine())


def targets(name: str | None = None) -> list[dict]:
    """The languages sentences can be translated to, by an engine (the one of the settings by default)."""
    languages = _languages(name or engine())
    return [{"id": key, "name": LANGUAGES[key]} for key in LANGUAGES if key in languages]


def target_language() -> str:
    """The language sentences are translated to ("" when they aren't), from the settings."""
    target = get_config().get("translation_language", DEFAULT_TARGET)
    return target if target == "" or translatable(target) else DEFAULT_TARGET


def _code(language: str, text: str = "") -> str:
    """Argos and NLLB have a code for traditional Chinese ("zt") besides simplified ("zh")."""
    if language == "zh" and text and chinese_script(text) == "traditional":
        return "zt"
    return language


def _source_codes(language: str) -> list[str]:
    """Argos codes of a language's text: Chinese has a model per script, the ones the user reads."""
    if language != "zh":
        return [language]
    return {"traditional": ["zt"], "simplified": ["zh"]}.get(chinese_script_preference("zh"), ["zt", "zh"])


def _missing(source: str, target: str) -> list[tuple[str, str]]:
    """The models still needed from source to target, through English when there's no direct one."""
    installed = argos.installed()
    if (source, target) in installed:
        return []
    pairs = [(source, target)] if argos.has_model(source, target) else [(source, "en"), ("en", target)]
    return [pair for pair in pairs if pair not in installed]


def engine_installed(name: str) -> bool:
    """Whether the engine can translate: its packages are there, and for NLLB its model is downloaded."""
    if name == ARGOS:
        return argos.available()
    return nllb.available() and nllb.installed(name)


class ModelDownload:
    """In the background: the download of the Argos models translating a language to the one of the settings, or the
    install of an NLLB model (its packages, then the model)."""

    def __init__(self):
        self.state = {"state": "idle", "language": "", "engine": "", "done": 0, "total": 0, "error": None}

    @property
    def running(self) -> bool:
        return self.state["state"] == "running"

    def start(self, language: str = "", engine: str = "") -> None:
        self.state.update(state="running", language=language, engine=engine, step="", done=0, total=0, error=None)
        threading.Thread(target=self._run, args=(language, engine), daemon=True,
                         name="miningcat-translate-models").start()

    def _progress(self, done: int, total: int) -> None:
        self.state.update(done=done, total=total)

    def _run(self, language: str, engine: str) -> None:
        try:
            with _lock:
                if engine:
                    self._install(engine)
                else:
                    self._download(language)
            self.state.update(state="done")
        except Exception as exc:
            self.state.update(state="error", error=str(exc))

    def _download(self, language: str) -> None:
        target = _code(target_language())
        pairs = list(dict.fromkeys(pair for code in _source_codes(language) for pair in _missing(code, target)))
        for index, pair in enumerate(pairs):
            self.state.update(step=f"{index + 1}/{len(pairs)}", done=0, total=0)
            argos.install(*pair, progress=self._progress)

    def _install(self, engine: str) -> None:
        if not nllb.available():
            self.state.update(step="packages")
            if nllb_install.install_packages() != 0:
                raise TranslateError("The packages couldn't be installed: see pip's output in the terminal.")
        self.state.update(step="model")
        nllb.install(engine, progress=self._progress)


_download = ModelDownload()


def engines() -> list[dict]:
    """The engines, whether each is installed, and the size of NLLB's models."""
    return [{"id": name, "label": label, "installed": engine_installed(name),
             "size": NLLB_MODELS[name].size if name in NLLB_MODELS else 0} for name, label in ENGINES.items()]


def models() -> dict:
    """The engines, the installed models, and the download in progress."""
    common = {"engine": engine(), "engines": engines(), "nllb": nllb.installed_models(), "job": dict(_download.state)}
    if not argos.available():
        return {"available": False, "installed": [], **common}
    installed = sorted(argos.installed_models(), key=lambda m: m["name"])
    return {"available": True, "installed": installed, **common}


def start_install(name: str) -> None:
    """Installs an NLLB model, in the background (its packages first when they're missing)."""
    if name not in NLLB_MODELS:
        raise TranslateError(f"Unknown translation model: {name!r}")
    if _download.running:
        raise TranslateError("A model is already being downloaded.")
    if engine_installed(name):
        raise TranslateError(f"{ENGINES[name]} is already installed.")
    _download.start(engine=name)


def start_download(language: str) -> None:
    """Downloads, in the background, what translates a language to the one of the settings: the Argos models, or the
    NLLB model of the settings (one for every language)."""
    target = target_language()
    if not translatable(language):
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if not target:
        raise TranslateError("Choose the language sentences are translated to first.")
    if language == target:
        raise TranslateError(f"Sentences are already translated to {LANGUAGES[target]}.")
    if engine() != ARGOS:
        start_install(engine())
        return
    if _download.running:
        raise TranslateError("A model is already being downloaded.")
    if not argos.available():
        raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
    _download.start(language)


def delete_model(source: str, target: str) -> None:
    with _lock:
        argos.uninstall(source, target)


def delete_engine(name: str) -> None:
    """Removes an NLLB model (its packages stay)."""
    if name not in NLLB_MODELS:
        raise TranslateError(f"Unknown translation model: {name!r}")
    with _lock:
        nllb.uninstall(name)


def _translate_nllb(name: str, lines: list[str], source: str, target: str) -> list[str]:
    if not nllb.available():
        raise TranslateError(f"{ENGINES[name]} isn't installed: install it in Settings › Translation, "
                             f"or with `{nllb_install.MAKE_TARGET}`.")
    try:
        return nllb.translate(name, lines, source, target)
    except TranslateError:
        raise
    except Exception as exc:
        raise TranslateError(f"The sentence couldn't be translated: {exc}")


def translate(language: str, text: str, download: bool = True) -> str | None:
    """The text translated to the language of the settings, or None when there's nothing to do. Without `download`
    (translated ahead of time, when a word is looked up), only with the models already installed. NLLB's model is
    never downloaded here: it's installed from the settings."""
    target = target_language()
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or not target or target == language:
        return None
    if not translatable(language):
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if len(text) > MAX_CHARS:
        raise TranslateError(f"Sentences are limited to {MAX_CHARS} characters.")
    source, target = _code(language, text), _code(target)
    if engine() != ARGOS:
        return _translate_nllb(engine(), [text], source, target)[0]
    argos.require()
    if not download:
        installed = argos.installed()
        if (source, target) not in installed and not {(source, "en"), ("en", target)} <= installed:
            raise TranslateError("The translation model isn't installed yet.")
    with _lock:
        try:
            for pair in _missing(source, target):
                argos.install(*pair)
            return argos.translate(text, source, target)
        except TranslateError:
            raise
        except OSError as exc:
            raise TranslateError(f"The translation model couldn't be downloaded: {exc}")
        except Exception as exc:
            raise TranslateError(f"The sentence couldn't be translated: {exc}")


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


def _translate_lines_nllb(name: str, source: str, target: str, lines: list[str],
                          progress: Callable[[int, int], None] | None) -> list[str]:
    """In batches: NLLB translates several lines at once faster than one by one."""
    translated = []
    for start in range(0, len(lines), NLLB_LINES_PER_STEP):
        batch = _translate_nllb(name, lines[start:start + NLLB_LINES_PER_STEP], source, target)
        translated += [re.sub(r"\s+", " ", line).strip() for line in batch]
        if progress:
            progress(len(translated), len(lines))
    return translated


def translate_lines(language: str, lines: list[str],
                    progress: Callable[[int, int], None] | None = None) -> list[str]:
    """Lines (of subtitles) translated to the language of the settings, the models downloaded first if needed.
    `progress(done, total)` after each line (each batch with NLLB)."""
    target = check(language)
    # The script of the whole text tells traditional from simplified Chinese better than a short line's.
    source, target = _code(language, "".join(lines)), _code(target)
    if engine() != ARGOS:
        return _translate_lines_nllb(engine(), source, target, lines, progress)
    argos.require()
    try:
        with _lock:
            for pair in _missing(source, target):
                argos.install(*pair)
    except TranslateError:
        raise
    except Exception as exc:
        raise TranslateError(f"The translation model couldn't be downloaded: {exc}")
    translated = []
    for line in lines:
        with _lock:
            try:
                translated.append(re.sub(r"\s+", " ", argos.translate(line, source, target)).strip())
            except Exception as exc:
                raise TranslateError(f"The subtitles couldn't be translated: {exc}")
        if progress:
            progress(len(translated), len(lines))
    return translated


def translate_srt(language: str, srt: str, progress: Callable[[int, int], None] | None = None) -> str:
    """SRT subtitles translated to the language of the settings: the same numbers, timestamps and formatting."""
    lines = srt_lines(srt)
    if not lines:
        raise TranslateError("These subtitles have no text to translate.")
    return replace_srt_lines(srt, dict(zip(lines, translate_lines(language, lines, progress))))
