"""The sound of a capture's line, asked for by the video game page (through MiningCat's server) to the capture server,
which records it (see capture_audio.py): `base_url` is the capture server's address."""
import json
import urllib.error
import urllib.parse
import urllib.request

from miningcat.domain.library.errors import AudioError
from miningcat.infrastructure.media.audio_clip import encode

_TIMEOUT_S = 10


def _request(base_url: str, path: str, method: str = "GET") -> bytes:
    try:
        with urllib.request.urlopen(urllib.request.Request(base_url + path, method=method), timeout=_TIMEOUT_S) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read()).get("error")
        except ValueError:
            message = None
        raise AudioError(message or f"The capture answered {exc.code}.")
    except (urllib.error.URLError, OSError):
        raise AudioError("The capture isn't running any more: its sound is gone.")


def info(base_url: str, capture_id: str) -> dict:
    """{id, duration, start, end}: the capture's clip, and its line's span in it (s)."""
    return json.loads(_request(base_url, f"audio/{urllib.parse.quote(capture_id)}", method="POST"))


def clip(base_url: str, capture_id: str, start, end, fmt: str = "mp3") -> bytes:
    """A span of the capture's clip (s, from its start), as MP3 for the card, or WAV for the waveform."""
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        raise AudioError("Invalid time span.")
    if end <= start:
        raise AudioError("Invalid time span.")
    query = urllib.parse.urlencode({"start": f"{start:.3f}", "end": f"{end:.3f}"})
    return encode(_request(base_url, f"audio/{urllib.parse.quote(capture_id)}.wav?{query}"), fmt)
