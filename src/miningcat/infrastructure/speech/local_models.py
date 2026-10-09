"""What the local speech engines share. They cover the languages Whisper and Edge don't: Taigi is transcribed with
Qwen3-ASR (qwen3_asr.py), aligned on its book with Meta's MMS aligner (mms_aligner.py) and read by Meta's MMS voice
(mms_tts.py). Their models are downloaded from Hugging Face the first time they're used, and their
packages are installed with `make install-taigi`, or `make install-qwen` for Qwen3-ASR alone (it can also replace
Whisper for the languages it knows). Once downloaded, they're loaded from the cache without contacting
huggingface.co."""

import os
import subprocess

import numpy as np

from miningcat.infrastructure.media.audio_files import AUDIO_BITRATE

SAMPLE_RATE = 16000

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


class SpeechError(RuntimeError):
    pass


def require(module: str, purpose: str, install: str = "make install-qwen"):
    """Imports an optional package, or explains how to install it (`install`: the command installing it)."""
    import importlib
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise SpeechError(f"{purpose} needs the {module} package ({exc}). Install it with `{install}`.") from exc


def local_model(repo: str) -> str:
    """The folder of a Hugging Face model in the local cache: loaded from there, it doesn't ask huggingface.co whether
    the model changed. The repo's name when it isn't downloaded yet (loading it downloads it)."""
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(repo, local_files_only=True)
    except (ImportError, OSError):  # not downloaded yet: LocalEntryNotFoundError is an OSError
        return repo


def load_audio(path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """The audio of a file (any format ffmpeg reads) as mono float32 samples."""
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-"],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise SpeechError(f"ffmpeg couldn't read {path}: {result.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(result.stdout, dtype=np.float32).copy()


def encode_mp3(samples: np.ndarray, sample_rate: int, path=None) -> bytes:
    """MP3 of mono float32 samples, written to `path` when given."""
    output = str(path) if path is not None else "-"
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-i", "-",
         "-codec:a", "libmp3lame", "-b:a", AUDIO_BITRATE, "-f", "mp3", output],
        input=np.asarray(samples, dtype=np.float32).tobytes(), capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise SpeechError(f"ffmpeg couldn't encode the audio: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def torch_device(allow_mps: bool = True) -> str:
    """cuda when there's an NVIDIA GPU, mps on Apple Silicon (when the model works with it), else cpu."""
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if allow_mps and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
