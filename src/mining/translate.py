import json
import re
import tempfile
import threading
import urllib.request
from pathlib import Path

from mining.languages import LANGUAGES, chinese_script
from mining.word_audio import USER_AGENT, _ssl_context

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
DEFAULT_TARGET = "en"
MAX_CHARS = 1000
# Languages Argos can translate (Cantonese and Taigi have no model).
ARGOS_LANGUAGES = {"zh", "ja", "ko", "en", "fr", "de", "es", "it", "pt", "pl", "ru", "vi"}

_lock = threading.Lock()
_index: list[dict] | None = None


class TranslateError(Exception):
    pass


def targets() -> list[dict]:
    return [{"id": key, "name": LANGUAGES[key]} for key in LANGUAGES if key in ARGOS_LANGUAGES]


def target_language() -> str:
    """The language sentences are translated to ("" when they aren't), from the settings."""
    from mining import anki

    target = anki.get_config().get("translation_language", DEFAULT_TARGET)
    return target if target == "" or target in ARGOS_LANGUAGES else DEFAULT_TARGET


# Argos has a model for traditional Chinese ("zt") besides simplified ("zh").
def _argos_code(language: str, text: str = "") -> str:
    if language == "zh" and text and chinese_script(text) == "traditional":
        return "zt"
    return language


def _download(url: str, timeout: float = 300) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return response.read()


def _available() -> list[dict]:
    global _index
    if _index is None:
        _index = json.loads(_download(INDEX_URL, timeout=20).decode("utf-8"))
    return _index


def _installed() -> set[tuple[str, str]]:
    import argostranslate.package

    return {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}


def _install(source: str, target: str) -> None:
    import argostranslate.package

    package = next((p for p in _available() if p["from_code"] == source and p["to_code"] == target), None)
    if package is None:
        raise TranslateError(f"There's no translation model from {source} to {target}.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{package['code']}.argosmodel"
        path.write_bytes(_download(package["links"][0]))
        argostranslate.package.install_from_path(path)


def _ensure_models(source: str, target: str) -> None:
    """Downloads the models from source to target, through English when there's no direct one."""
    installed = _installed()
    if (source, target) in installed:
        return
    direct = any(p["from_code"] == source and p["to_code"] == target for p in _available())
    pairs = [(source, target)] if direct else [(source, "en"), ("en", target)]
    for pair in pairs:
        if pair not in installed:
            _install(*pair)


def translate(language: str, text: str) -> str | None:
    """The text translated to the language of the settings, or None when there's nothing to do."""
    target = target_language()
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or not target or target == language:
        return None
    if language not in ARGOS_LANGUAGES:
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if len(text) > MAX_CHARS:
        raise TranslateError(f"Sentences are limited to {MAX_CHARS} characters.")
    try:
        import argostranslate.translate
    except ImportError:
        raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
    source, target = _argos_code(language, text), _argos_code(target)
    with _lock:  # one download and one model load at a time
        try:
            _ensure_models(source, target)
            return argostranslate.translate.translate(text, source, target)
        except TranslateError:
            raise
        except OSError as exc:
            raise TranslateError(f"The translation model couldn't be downloaded: {exc}")
        except Exception as exc:
            raise TranslateError(f"The sentence couldn't be translated: {exc}")
