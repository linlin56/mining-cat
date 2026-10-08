import re
import threading

from miningcat.application.anki.config import get_config
from miningcat.application.mining.preferences import chinese_script_preference
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.text.chinese_script import chinese_script
from miningcat.infrastructure.translation.argos import LANGUAGES as ARGOS_LANGUAGES
from miningcat.infrastructure.translation.argos import ArgosTranslate, TranslateError

DEFAULT_TARGET = "en"
MAX_CHARS = 1000

argos = ArgosTranslate()
# One download and one model load at a time.
_lock = threading.Lock()


def targets() -> list[dict]:
    """The languages sentences can be translated to."""
    return [{"id": key, "name": LANGUAGES[key]} for key in LANGUAGES if key in ARGOS_LANGUAGES]


def target_language() -> str:
    """The language sentences are translated to ("" when they aren't), from the settings."""
    target = get_config().get("translation_language", DEFAULT_TARGET)
    return target if target == "" or target in ARGOS_LANGUAGES else DEFAULT_TARGET


def _argos_code(language: str, text: str = "") -> str:
    """Argos has a model for traditional Chinese ("zt") besides simplified ("zh")."""
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


class ModelDownload:
    """The download of the models translating a language to the one of the settings, in the background."""

    def __init__(self):
        self.state = {"state": "idle", "language": "", "done": 0, "total": 0, "error": None}

    @property
    def running(self) -> bool:
        return self.state["state"] == "running"

    def start(self, language: str) -> None:
        self.state.update(state="running", language=language, done=0, total=0, error=None)
        threading.Thread(target=self._run, args=(language,), daemon=True, name="miningcat-translate-models").start()

    def _run(self, language: str) -> None:
        try:
            with _lock:
                target = _argos_code(target_language())
                pairs = list(dict.fromkeys(pair for code in _source_codes(language) for pair in _missing(code, target)))
                for index, pair in enumerate(pairs):
                    self.state.update(step=f"{index + 1}/{len(pairs)}", done=0, total=0)
                    argos.install(*pair, progress=lambda done, total: self.state.update(done=done, total=total))
            self.state.update(state="done")
        except Exception as exc:
            self.state.update(state="error", error=str(exc))


_download = ModelDownload()


def models() -> dict:
    """The installed models, and the download in progress."""
    if not argos.available():
        return {"available": False, "installed": [], "job": dict(_download.state)}
    installed = sorted(argos.installed_models(), key=lambda m: m["name"])
    return {"available": True, "installed": installed, "job": dict(_download.state)}


def start_download(language: str) -> None:
    """Downloads, in the background, the models translating a language to the one of the settings."""
    target = target_language()
    if language not in ARGOS_LANGUAGES:
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if not target:
        raise TranslateError("Choose the language sentences are translated to first.")
    if language == target:
        raise TranslateError(f"Sentences are already translated to {LANGUAGES[target]}.")
    if _download.running:
        raise TranslateError("A model is already being downloaded.")
    if not argos.available():
        raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
    _download.start(language)


def delete_model(source: str, target: str) -> None:
    with _lock:
        argos.uninstall(source, target)


def translate(language: str, text: str, download: bool = True) -> str | None:
    """The text translated to the language of the settings, or None when there's nothing to do. Without `download`
    (translated ahead of time, when a word is looked up), only with the models already installed."""
    target = target_language()
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or not target or target == language:
        return None
    if language not in ARGOS_LANGUAGES:
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if len(text) > MAX_CHARS:
        raise TranslateError(f"Sentences are limited to {MAX_CHARS} characters.")
    argos.require()
    source, target = _argos_code(language, text), _argos_code(target)
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
