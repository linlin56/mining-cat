"""The sound of each capture's line, for the card creator: the recording around the capture (seconds before and after
it), cut out of the ring once the line is over, with where its voice probably is."""
import io
import wave
from dataclasses import dataclass

import numpy as np

from miningcat.domain.audio.voice import line_span, voiced_spans
from miningcat.infrastructure.capture.audio import AudioRing

# The recording kept around a capture: the line is in there, said before the key was pressed, or after its text appeared.
BEFORE_S = 15.0
AFTER_S = 15.0
# The page replays the last 20 captures: older ones lose their sound.
KEEP = 20


@dataclass
class _Clip:
    at: float
    appeared: bool
    end: float                       # clock time the clip ends at: AFTER_S after `at`, or earlier (see add())
    start: float = 0.0               # clock time of its first sample, once cut
    samples: np.ndarray | None = None  # cut out of the ring once `end` is past
    span: tuple[float, float] = (0.0, 0.0)  # the line in the clip (s)


class CaptureAudio:
    """The clips of the last KEEP captures, by capture id. Only used from the capture server's event loop."""

    def __init__(self, ring: AudioRing):
        self._ring = ring
        self._clips: dict[str, _Clip] = {}

    def add(self, capture_id: str, at: float, appeared: bool) -> list[dict]:
        """A new capture, whose line was said at `at` (see CaptureResult). The previous lines are over: their clips end
        when this one started, and are cut. Returns their info()."""
        cut = []
        for previous_id, clip in self._clips.items():
            if clip.samples is None:
                clip.end = min(clip.end, max(at, clip.at))
                cut.append(previous_id)
        self._clips[capture_id] = _Clip(at=at, appeared=appeared, end=at + AFTER_S)
        while len(self._clips) > KEEP:
            del self._clips[next(iter(self._clips))]
        return [self.cut(previous_id) for previous_id in cut]

    def due(self) -> list[str]:
        """Captures whose clip is over but not cut yet."""
        now = self._ring.now()
        return [capture_id for capture_id, clip in self._clips.items() if clip.samples is None and clip.end <= now]

    def cut(self, capture_id: str) -> dict | None:
        """Cuts the capture's clip out of the ring (ending now, if it isn't over yet: the card is being made), and tells
        it: {id, duration, start, end}, the line's span in the clip (s). None for a capture too old, or unknown."""
        clip = self._clips.get(capture_id)
        if clip is None:
            return None
        if clip.samples is None:
            clip.end = min(clip.end, self._ring.now())
            clip.start, clip.samples = self._ring.read(clip.at - BEFORE_S, clip.end)
            duration = len(clip.samples) / self._ring.rate
            clip.span = line_span(voiced_spans(clip.samples, self._ring.rate), clip.at - clip.start, clip.appeared, duration)
        return {"id": capture_id, "duration": round(len(clip.samples) / self._ring.rate, 3),
                "start": round(clip.span[0], 3), "end": round(clip.span[1], 3)}

    def wav(self, capture_id: str, start: float, end: float) -> bytes | None:
        """A span of the capture's clip (s, from its start) as 16-bit WAV. None for a capture too old, or unknown."""
        if self.cut(capture_id) is None:
            return None
        clip = self._clips[capture_id]
        rate = self._ring.rate
        first = max(0, round(start * rate))
        last = min(len(clip.samples), max(first, round(end * rate)))
        pcm = (np.clip(clip.samples[first:last], -1.0, 1.0) * 32767).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            out.writeframes(pcm.tobytes())
        return buffer.getvalue()
