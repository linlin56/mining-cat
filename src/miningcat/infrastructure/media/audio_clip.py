import subprocess
from pathlib import Path

from miningcat.domain.library.errors import AudioError

# A little silence around a cut sentence, so that its first and last sounds aren't clipped.
CLIP_PADDING_S = 0.15

# MP3 for cards; WAV (16 kHz, 16 bits) for the card creator's waveform: decoded exactly, with no encoder delay.
_CODECS = {"mp3": ["-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3"],
           "wav": ["-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav"]}


def cut_mp3(source: Path, start: float, end: float, audio_stream: int = 0,
            before: float = CLIP_PADDING_S, after: float = CLIP_PADDING_S, fmt: str = "mp3") -> bytes:
    """The span of an audio (or video) file as MP3 (or WAV), cut with ffmpeg. Constant bitrate: written to a pipe, a
    variable bitrate MP3 has no header giving its length, and players would show a wrong duration."""
    start = max(0.0, float(start) - before)
    end = float(end) + after
    if end <= start:
        raise AudioError("Invalid time span.")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
             "-i", str(source), "-map", f"0:a:{audio_stream}", "-vn", "-ac", "1", *_CODECS[fmt], "pipe:1"],
            capture_output=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        raise AudioError("ffmpeg isn't installed: it's needed to cut the sentence's audio.")
    except subprocess.CalledProcessError as exc:
        raise AudioError(f"ffmpeg couldn't cut the audio: {exc.stderr.decode(errors='replace').strip()[:300]}")
    except subprocess.TimeoutExpired:
        raise AudioError("ffmpeg took too long to cut the audio.")
    return result.stdout
