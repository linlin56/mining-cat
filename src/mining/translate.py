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


def _download(url: str, timeout: float = 300, progress=None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        total = int(response.headers.get("Content-Length") or 0)
        data = bytearray()
        while chunk := response.read(256 * 1024):
            data.extend(chunk)
            if progress:
                progress(len(data), total)
        return bytes(data)


def _available() -> list[dict]:
    global _index
    if _index is None:
        _index = json.loads(_download(INDEX_URL, timeout=20).decode("utf-8"))
    return _index


def _installed() -> set[tuple[str, str]]:
    import argostranslate.package

    return {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}


def _install(source: str, target: str, progress=None) -> None:
    import argostranslate.package

    package = next((p for p in _available() if p["from_code"] == source and p["to_code"] == target), None)
    if package is None:
        raise TranslateError(f"There's no translation model from {source} to {target}.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"{package['code']}.argosmodel"
        path.write_bytes(_download(package["links"][0], progress=progress))
        argostranslate.package.install_from_path(path)


def _missing(source: str, target: str) -> list[tuple[str, str]]:
    """The models still needed from source to target, through English when there's no direct one."""
    installed = _installed()
    if (source, target) in installed:
        return []
    direct = any(p["from_code"] == source and p["to_code"] == target for p in _available())
    pairs = [(source, target)] if direct else [(source, "en"), ("en", target)]
    return [pair for pair in pairs if pair not in installed]


def _ensure_models(source: str, target: str) -> None:
    for pair in _missing(source, target):
        _install(*pair)


# ---------------------------------------------------------------- models, managed from the settings

_job = {"state": "idle", "language": "", "done": 0, "total": 0, "error": None}


def _source_codes(language: str) -> list[str]:
    """Argos codes of a language's text: Chinese has a model per script, the ones the user reads."""
    if language != "zh":
        return [language]
    from mining.words import chinese_script_preference

    return {"traditional": ["zt"], "simplified": ["zh"]}.get(chinese_script_preference("zh"), ["zt", "zh"])


def models() -> dict:
    """The installed models, and the download in progress."""
    try:
        import argostranslate.package
    except ImportError:
        return {"available": False, "installed": [], "job": dict(_job)}
    installed = []
    for package in argostranslate.package.get_installed_packages():
        path = Path(package.package_path)
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        installed.append({"from": package.from_code, "to": package.to_code,
                          "name": f"{package.from_name} → {package.to_name}", "size": size})
    return {"available": True, "installed": sorted(installed, key=lambda m: m["name"]), "job": dict(_job)}


def start_download(language: str) -> None:
    """Downloads, in the background, the models translating a language to the one of the settings."""
    target = target_language()
    if language not in ARGOS_LANGUAGES:
        raise TranslateError(f"There's no offline translation for {LANGUAGES.get(language, language)}.")
    if not target:
        raise TranslateError("Choose the language sentences are translated to first.")
    if language == target:
        raise TranslateError(f"Sentences are already translated to {LANGUAGES[target]}.")
    if _job["state"] == "running":
        raise TranslateError("A model is already being downloaded.")
    try:
        import argostranslate.package  # noqa: F401
    except ImportError:
        raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
    _job.update(state="running", language=language, done=0, total=0, error=None)

    def run():
        try:
            with _lock:
                pairs = [pair for code in _source_codes(language) for pair in _missing(code, _argos_code(target))]
                for index, pair in enumerate(dict.fromkeys(pairs)):
                    _job.update(step=f"{index + 1}/{len(set(pairs))}", done=0, total=0)
                    _install(*pair, progress=lambda done, total: _job.update(done=done, total=total))
            _job.update(state="done")
        except Exception as exc:
            _job.update(state="error", error=str(exc))

    threading.Thread(target=run, daemon=True, name="miningcat-translate-models").start()


def delete_model(source: str, target: str) -> None:
    import argostranslate.package

    package = next((p for p in argostranslate.package.get_installed_packages()
                    if p.from_code == source and p.to_code == target), None)
    if package is None:
        raise TranslateError("This model isn't installed.")
    with _lock:
        argostranslate.package.uninstall(package)


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
