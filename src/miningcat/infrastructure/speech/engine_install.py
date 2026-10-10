"""The packages of the local speech engines, installed with `make install-qwen` / `make install-taigi` or by the
converter, which offers it when a language needs them. Qwen3-ASR is optional for the languages Whisper knows; Taigi
needs it (its transcriber) and Meta's MMS (its voice and aligner)."""
import importlib.util
import subprocess

from miningcat.config.paths import PROJECT_ROOT
from miningcat.config.runtime import PYTHON
from miningcat.infrastructure.speech import qwen3_asr

QWEN, TAIGI = "qwen", "taigi"
# Installed apart, with --no-deps: it pins packages that don't build on recent Pythons (nagisa) and others only its
# demos use (gradio, vllm). Same version as the Makefile's.
QWEN_ASR_REQUIREMENT = "qwen-asr==0.0.6"


def _pip(*args: str) -> list[str]:
    return [PYTHON, "-m", "pip", "install", *args]


def commands(engines: str) -> list[list[str]]:
    """The pip commands installing `engines` (QWEN or TAIGI): Taigi's start with Qwen3-ASR's."""
    qwen = [_pip("-r", str(PROJECT_ROOT / "requirements-qwen.txt")), _pip("--no-deps", QWEN_ASR_REQUIREMENT)]
    if engines == QWEN:
        return qwen
    if engines == TAIGI:
        return qwen + [_pip("-r", str(PROJECT_ROOT / "requirements-taigi.txt"))]
    raise ValueError(f"Unknown engines: {engines!r}")


def installed(engines: str) -> bool:
    """Whether `engines` are installed: Qwen3-ASR, and for Taigi the transformers MMS's voice runs with."""
    return qwen3_asr.installed() and (engines == QWEN or importlib.util.find_spec("transformers") is not None)


def install(engines: str) -> int:
    """Installs the packages, pip's output going to this process's. Returns the exit code of the first command that
    fails, else 0."""
    for command in commands(engines):
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            return returncode
    return 0
