"""The install of NLLB-200, which translates the sentences and subtitles (optional, large): its packages (CTranslate2,
which faster-whisper brings already, and SentencePiece), then its model. With `make install-nllb`
(python -m miningcat install-nllb), or from the settings."""
import subprocess
from typing import Callable

from miningcat.config.paths import PROJECT_ROOT
from miningcat.config.runtime import PYTHON
from miningcat.infrastructure.translation.nllb import Nllb

MAKE_TARGET = "make install-nllb"


def commands() -> list[list[str]]:
    """The pip commands installing its packages. Same as the Makefile's."""
    return [[PYTHON, "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements-nllb.txt")]]


def install_packages() -> int:
    """Installs the packages, pip's output going to this process's. Returns the exit code of the first command that
    fails, else 0."""
    for command in commands():
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            return returncode
    return 0


def install(model: str, progress: Callable[[int, int], None] | None = None) -> int:
    """Installs the packages, then downloads the model (unless it's there). Returns pip's exit code when it fails."""
    returncode = install_packages()
    if returncode == 0:
        nllb = Nllb()
        if not nllb.installed(model):
            nllb.install(model, progress)
    return returncode
