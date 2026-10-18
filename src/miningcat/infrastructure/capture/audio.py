import threading
import time
from typing import Callable

import numpy as np

# The recording kept in memory, for the lines of the last captures (it's never written to disk).
RING_S = 120
# A chunk arriving later than its own length plus this is after a gap (the OS sends nothing while nothing plays):
# the gap is filled with silence, so that the recording's times stay those of the clock.
_GAP_TOLERANCE_S = 0.05


class AudioRing:
    """The last RING_S seconds of a mono recording, written as it arrives (from the OS's audio thread) and read by
    the time of `clock`, the same clock as the captures' times."""

    def __init__(self, rate: int, seconds: float = RING_S, clock: Callable[[], float] = time.monotonic):
        self.rate = rate
        self._clock = clock
        self._data = np.zeros(round(rate * seconds), dtype=np.float32)
        self._written = 0          # samples written since the start
        self._last_time: float | None = None  # clock time of the last sample written
        self._lock = threading.Lock()

    def now(self) -> float:
        return self._clock()

    # A chunk of float32 samples, just received: it ends now.
    def write(self, samples: np.ndarray) -> None:
        samples = np.asarray(samples, dtype=np.float32).ravel()
        with self._lock:
            now = self._clock()
            if self._last_time is not None:
                gap = now - len(samples) / self.rate - self._last_time
                if gap > _GAP_TOLERANCE_S:
                    self._append(np.zeros(min(len(self._data), round(gap * self.rate)), dtype=np.float32))
            self._append(samples)
            self._last_time = now

    def _append(self, samples: np.ndarray) -> None:
        size = len(self._data)
        samples = samples[-size:]
        at = self._written % size
        first = min(len(samples), size - at)
        self._data[at:at + first] = samples[:first]
        self._data[:len(samples) - first] = samples[first:]
        self._written += len(samples)

    def read(self, start: float, end: float) -> tuple[float, np.ndarray]:
        """The samples between two clock times, as far as they're still (or already) recorded, and the clock time of
        the first one: later than `start` when it's older than what's kept."""
        with self._lock:
            if self._last_time is None:
                return start, np.zeros(0, dtype=np.float32)
            size = len(self._data)
            first = max(self._written - size, self._written - round((self._last_time - start) * self.rate), 0)
            last = min(self._written, self._written - round((self._last_time - end) * self.rate))
            first_time = self._last_time - (self._written - first) / self.rate
            if last <= first:
                return first_time, np.zeros(0, dtype=np.float32)
            return first_time, self._data[np.arange(first, last) % size].copy()


class AudioRecorder:
    """Records the sound of the captured window (its app) into `ring`, from start() until close()."""

    def __init__(self, rate: int):
        self.ring = AudioRing(rate)

    def start(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
