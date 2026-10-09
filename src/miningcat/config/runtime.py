import platform
import sys
from pathlib import Path

from miningcat.config.paths import PROJECT_ROOT

# config/ -> miningcat/ -> src/: the folder to run `python -m miningcat...` from.
SRC_DIR = Path(__file__).resolve().parents[2]

_VENV_PYTHON = (
    PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if platform.system() == "Windows"
    else PROJECT_ROOT / ".venv" / "bin" / "python3"
)
# The interpreter running the background processes (pipelines, video game capture, OCR worker).
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable


def module_command(module: str, *args: str) -> list[str]:
    """Command line running a module of the package in a new process (from SRC_DIR)."""
    return [PYTHON, "-m", module, *args]
