"""The translation models, and their install (optional, large): the packages of their engine first, then the model.
NLLB-200 needs CTranslate2 (which faster-whisper brings already) and SentencePiece (requirements-nllb.txt); Qwen3
needs transformers, like Qwen3-ASR (requirements-qwen.txt). With `make install-translation`
(python -m miningcat install-translation), or from the settings."""
import subprocess
from typing import Callable

from miningcat.config.paths import PROJECT_ROOT
from miningcat.config.runtime import PYTHON
from miningcat.infrastructure.translation.nllb import Nllb
from miningcat.infrastructure.translation.qwen3 import Qwen3

MAKE_TARGET = "make install-translation"
# Each engine, with the requirements of its packages.
ENGINES = {Nllb: "requirements-nllb.txt", Qwen3: "requirements-qwen.txt"}
MODELS = {name: model for engine in ENGINES for name, model in engine.MODELS.items()}
DEFAULT_MODEL = "nllb-600m"


def engine_of(name: str) -> type:
    return next(engine for engine in ENGINES if name in engine.MODELS)


def commands(name: str) -> list[list[str]]:
    """The pip commands installing the packages of a model's engine. Same as the Makefile's."""
    return [[PYTHON, "-m", "pip", "install", "-r", str(PROJECT_ROOT / ENGINES[engine_of(name)])]]


def install_packages(name: str) -> int:
    """Installs the packages of a model's engine, pip's output going to this process's. Returns the exit code of the
    first command that fails, else 0."""
    for command in commands(name):
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            return returncode
    return 0


def install(name: str, progress: Callable[[int, int], None] | None = None) -> int:
    """Installs the packages, then downloads the model (unless it's there). Returns pip's exit code when it fails."""
    returncode = install_packages(name)
    if returncode == 0:
        engine = engine_of(name)
        if not engine.installed(name):
            engine.install(name, progress)
    return returncode
