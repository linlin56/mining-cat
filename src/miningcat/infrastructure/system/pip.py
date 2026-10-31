"""pip's commands, as `make install` and the installs of the engines run them: one at a time, pip's output going to
this process's."""
import platform
import shutil
import subprocess

from miningcat.config.runtime import PYTHON

# On Linux without an NVIDIA GPU, PyTorch's default build drags several GB of useless CUDA packages (as `make install`).
PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def install(*args: str, python: str = PYTHON) -> list[str]:
    """The command installing packages with pip (`args`: pip install's)."""
    return [str(python), "-m", "pip", "install", *args]


def cpu_pytorch() -> bool:
    """Whether PyTorch's CPU build is the one to install: Linux without an NVIDIA GPU."""
    return platform.system() == "Linux" and shutil.which("nvidia-smi") is None


def run(commands: list[list[str]]) -> int:
    """Runs the commands one after the other. Returns the exit code of the first one that fails, else 0."""
    for command in commands:
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            return returncode
    return 0
