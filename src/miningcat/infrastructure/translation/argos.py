import json
import tempfile
from pathlib import Path
from typing import Callable

from miningcat.infrastructure import http

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
# Languages Argos can translate (Cantonese and Taigi have no model). "zt" is its traditional Chinese.
LANGUAGES = {"zh", "ja", "ko", "en", "fr", "de", "es", "it", "pt", "pl", "ru", "vi"}


class TranslateError(Exception):
    pass


class ArgosTranslate:
    """Argos Translate: its models (one per language pair, downloaded from its index) and its translations."""

    def __init__(self):
        self._index: list[dict] | None = None

    @staticmethod
    def _package():
        try:
            import argostranslate.package
        except ImportError:
            raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
        return argostranslate.package

    def available(self) -> bool:
        try:
            self._package()
            return True
        except TranslateError:
            return False

    def index(self) -> list[dict]:
        """The models that can be downloaded."""
        if self._index is None:
            self._index = json.loads(http.download(INDEX_URL, timeout=20).decode("utf-8"))
        return self._index

    def has_model(self, source: str, target: str) -> bool:
        return any(p["from_code"] == source and p["to_code"] == target for p in self.index())

    def installed(self) -> set[tuple[str, str]]:
        return {(p.from_code, p.to_code) for p in self._package().get_installed_packages()}

    def installed_models(self) -> list[dict]:
        """{"from", "to", "name", "size"} of each installed model."""
        models = []
        for package in self._package().get_installed_packages():
            path = Path(package.package_path)
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            models.append({"from": package.from_code, "to": package.to_code,
                           "name": f"{package.from_name} → {package.to_name}", "size": size})
        return models

    def install(self, source: str, target: str, progress: Callable[[int, int], None] | None = None) -> None:
        package = next((p for p in self.index() if p["from_code"] == source and p["to_code"] == target), None)
        if package is None:
            raise TranslateError(f"There's no translation model from {source} to {target}.")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / f"{package['code']}.argosmodel"
            path.write_bytes(http.download(package["links"][0], progress=progress))
            self._package().install_from_path(path)

    def uninstall(self, source: str, target: str) -> None:
        argos_package = self._package()
        package = next((p for p in argos_package.get_installed_packages()
                        if p.from_code == source and p.to_code == target), None)
        if package is None:
            raise TranslateError("This model isn't installed.")
        argos_package.uninstall(package)

    @staticmethod
    def _translator():
        try:
            import argostranslate.translate
        except ImportError:
            raise TranslateError("Translation needs the argostranslate package (pip install argostranslate).")
        return argostranslate.translate

    def require(self) -> None:
        """Raises TranslateError when Argos Translate isn't installed."""
        self._translator()

    def translate(self, text: str, source: str, target: str) -> str:
        return self._translator().translate(text, source, target)
