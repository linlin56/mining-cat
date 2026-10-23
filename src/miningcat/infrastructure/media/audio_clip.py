import subprocess
from pathlib import Path

from miningcat.domain.library.errors import AudioError

# A little silence around a cut sentence, so that its first and last sounds aren't clipped.
CLIP_PADDING_S = 0.15

# MP3 for cards; WAV (16 kHz, 16 bits) for the card creator's waveform: decoded exactly, with no encoder delay.
_CODECS = {"mp3": ["-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3"],
           "wav": ["-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav"]}

# The channel layouts with a front center channel, where films and series put the voices.
_CENTER_LAYOUTS = {"3.0", "3.0(back)", "4.0", "4.1", "5.0", "5.0(side)", "5.1", "5.1(side)", "6.0", "6.1",
                   "6.1(back)", "7.0", "7.0(front)", "7.1", "7.1(wide)", "7.1(wide-side)", "hexagonal", "octagonal"}

# Films are mixed quietly, with room for the loud scenes: the clips are brought to the loudness of speech (as loud as
# the TTS), the rumble under the voices removed.
_LEVEL = "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11"


def _channel_layout(source: Path, audio_stream: int) -> str:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", f"a:{audio_stream}", "-show_entries", "stream=channel_layout",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, check=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.decode(errors="replace").strip()


def _mono_filter(source: Path, audio_stream: int) -> str:
    """The voices first: with a center channel, mostly it (a plain downmix makes them a fraction of the sound), the
    front ones a little for the context, without the surround ones and the bass. Otherwise all channels evenly."""
    if _channel_layout(source, audio_stream) in _CENTER_LAYOUTS:
        return f"pan=mono|c0<FC+0.3*FL+0.3*FR,{_LEVEL}"
    return f"aformat=channel_layouts=mono,{_LEVEL}"


def cut_mp3(source: Path, start: float, end: float, audio_stream: int = 0,
            before: float = CLIP_PADDING_S, after: float = CLIP_PADDING_S, fmt: str = "mp3") -> bytes:
    """The span of an audio (or video) file as MP3 (or WAV), cut with ffmpeg, its voices brought forward. Constant
    bitrate: written to a pipe, a variable bitrate MP3 has no header giving its length, and players would show a wrong
    duration."""
    start = max(0.0, float(start) - before)
    end = float(end) + after
    if end <= start:
        raise AudioError("Invalid time span.")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
             "-i", str(source), "-map", f"0:a:{audio_stream}", "-vn", "-af", _mono_filter(source, audio_stream),
             *_CODECS[fmt], "pipe:1"],
            capture_output=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        raise AudioError("ffmpeg isn't installed: it's needed to cut the sentence's audio.")
    except subprocess.CalledProcessError as exc:
        raise AudioError(f"ffmpeg couldn't cut the audio: {exc.stderr.decode(errors='replace').strip()[:300]}")
    except subprocess.TimeoutExpired:
        raise AudioError("ffmpeg took too long to cut the audio.")
    return result.stdout
