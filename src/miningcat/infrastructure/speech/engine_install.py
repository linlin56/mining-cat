"""The packages of the local speech engines, installed with `make install-qwen` / `make install-taigi` /
`make install-omnivoice` or by the converter, which offers it when a language needs them. Qwen3-ASR is optional for
the languages Whisper knows; Taigi needs it (its transcriber) and Meta's MMS (its voice and aligner). OmniVoice, the
local voice of every language, gets its own environment (.venv-omnivoice, see omnivoice_tts.py)."""
import importlib.util
import platform
import shutil
import subprocess

from miningcat.config.paths import PROJECT_ROOT
from miningcat.config.runtime import PYTHON
from miningcat.infrastructure.speech import omnivoice_tts, qwen3_asr

QWEN, TAIGI, OMNIVOICE = "qwen", "taigi", "omnivoice"
# Installed apart, with --no-deps: it pins packages that don't build on recent Pythons (nagisa) and others only its
# demos use (gradio, vllm). Same version as the Makefile's.
QWEN_ASR_REQUIREMENT = "qwen-asr==0.0.6"
# Installed apart, with --no-deps: it pins packages only its demo and its training use (gradio, tensorboardX...).
OMNIVOICE_REQUIREMENT = "omnivoice==0.2.1"
# On Linux without an NVIDIA GPU, PyTorch's default build drags several GB of useless CUDA packages (as `make install`).
PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def _pip(*args: str) -> list[str]:
    return [PYTHON, "-m", "pip", "install", *args]


def _omnivoice_commands() -> list[list[str]]:
    """.venv-omnivoice, then PyTorch, OmniVoice's packages and OmniVoice in it."""
    pip = [str(omnivoice_tts.PYTHON), "-m", "pip", "install"]
    pytorch = [*pip, "torch", "torchaudio"]
    if platform.system() == "Linux" and shutil.which("nvidia-smi") is None:
        pytorch += ["--index-url", PYTORCH_CPU_INDEX]
    return [
        [PYTHON, "-m", "venv", str(omnivoice_tts.VENV)],
        pytorch,
        [*pip, "-r", str(PROJECT_ROOT / "requirements-omnivoice.txt")],
        [*pip, "--no-deps", OMNIVOICE_REQUIREMENT],
    ]


def commands(engines: str) -> list[list[str]]:
    """The commands installing `engines` (QWEN, TAIGI or OMNIVOICE): Taigi's start with Qwen3-ASR's."""
    if engines == OMNIVOICE:
        return _omnivoice_commands()
    qwen = [_pip("-r", str(PROJECT_ROOT / "requirements-qwen.txt")), _pip("--no-deps", QWEN_ASR_REQUIREMENT)]
    if engines == QWEN:
        return qwen
    if engines == TAIGI:
        return qwen + [_pip("-r", str(PROJECT_ROOT / "requirements-taigi.txt"))]
    raise ValueError(f"Unknown engines: {engines!r}")


def installed(engines: str) -> bool:
    """Whether `engines` are installed: Qwen3-ASR, and for Taigi the transformers MMS's voice runs with; OmniVoice in
    its environment."""
    if engines == OMNIVOICE:
        return omnivoice_tts.installed()
    return qwen3_asr.installed() and (engines == QWEN or importlib.util.find_spec("transformers") is not None)


def install(engines: str) -> int:
    """Installs the packages, pip's output going to this process's. Returns the exit code of the first command that
    fails, else 0."""
    for command in commands(engines):
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            return returncode
    return 0
