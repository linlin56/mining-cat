import numpy as np
import pytest

from miningcat.infrastructure.capture.audio import AudioRing

RATE = 10


class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def _ring(seconds=5, clock=None):
    return AudioRing(RATE, seconds=seconds, clock=clock or Clock())


def _write(ring, clock, values):
    """Samples received now: they end at the clock's time."""
    clock.now += len(values) / RATE
    ring.write(np.array(values, dtype=np.float32))


def test_reads_by_clock_time():
    clock = Clock()
    ring = _ring(clock=clock)
    _write(ring, clock, range(10))  # 100.0 -> 101.0
    start, samples = ring.read(100.2, 100.5)
    assert start == pytest.approx(100.2)
    assert samples.tolist() == [2, 3, 4]


def test_reading_before_the_recording_starts_from_its_first_sample():
    clock = Clock()
    ring = _ring(clock=clock)
    _write(ring, clock, range(10))
    start, samples = ring.read(90, 100.3)
    assert start == pytest.approx(100.0)
    assert samples.tolist() == [0, 1, 2]


def test_reading_ahead_stops_at_the_last_sample():
    clock = Clock()
    ring = _ring(clock=clock)
    _write(ring, clock, range(10))
    assert ring.read(100.8, 120)[1].tolist() == [8, 9]
    assert ring.read(102, 103)[1].tolist() == []


def test_only_the_last_seconds_are_kept():
    clock = Clock()
    ring = _ring(seconds=1, clock=clock)
    _write(ring, clock, range(7))
    _write(ring, clock, range(7, 14))  # wraps around
    start, samples = ring.read(0, 200)
    assert samples.tolist() == list(range(4, 14))
    assert start == pytest.approx(clock.now - 1.0)


def test_a_gap_without_sound_is_filled_with_silence():
    clock = Clock()
    ring = _ring(clock=clock)
    _write(ring, clock, [1, 1])          # 100.0 -> 100.2
    clock.now += 0.3                     # nothing sent while nothing played
    _write(ring, clock, [2, 2])          # 100.5 -> 100.7
    assert ring.read(100.0, 100.7)[1].tolist() == [1, 1, 0, 0, 0, 2, 2]


def test_nothing_recorded_yet():
    start, samples = _ring().read(99, 101)
    assert (start, samples.tolist()) == (99, [])
