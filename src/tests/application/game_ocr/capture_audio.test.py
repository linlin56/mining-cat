import io
import wave

import numpy as np
import pytest

from miningcat.application.game_ocr import capture_audio
from miningcat.application.game_ocr.capture_audio import CaptureAudio
from miningcat.infrastructure.capture.audio import AudioRing

RATE = 1000


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def ring(clock):
    return AudioRing(RATE, seconds=60, clock=clock)


def _play(ring, clock, seconds, loudness=0.0):
    t = np.arange(round(seconds * RATE)) / RATE
    clock.now += seconds
    ring.write((loudness * np.sin(2 * np.pi * 50 * t)).astype(np.float32))


def test_line_found_after_its_text_appeared(ring, clock):
    _play(ring, clock, 20)               # 1000 -> 1020
    audio = CaptureAudio(ring)
    assert audio.add("1", at=1020.0, appeared=True) == []
    _play(ring, clock, 0.5)
    _play(ring, clock, 2.0, 0.3)          # the voice: 1020.5 -> 1022.5
    _play(ring, clock, 2.0)
    info = audio.cut("1")
    assert info["id"] == "1"
    # the clip starts BEFORE_S before the line, and ends now (a card is being made)
    assert info["duration"] == pytest.approx(capture_audio.BEFORE_S + 4.5, abs=0.01)
    assert info["start"] == pytest.approx(capture_audio.BEFORE_S + 0.5, abs=0.05)
    assert info["end"] == pytest.approx(capture_audio.BEFORE_S + 2.5, abs=0.05)


def test_the_next_capture_ends_the_previous_line(ring, clock):
    audio = CaptureAudio(ring)
    _play(ring, clock, 1)
    audio.add("1", at=clock.now, appeared=True)
    _play(ring, clock, 3, 0.3)
    _play(ring, clock, 1)
    cut = audio.add("2", at=clock.now - 0.5, appeared=True)
    assert [info["id"] for info in cut] == ["1"]
    assert cut[0]["duration"] == pytest.approx(1 + 3 + 0.5, abs=0.01)
    _play(ring, clock, 5, 0.3)
    assert audio.cut("1") == cut[0]  # cut once: the later sound isn't in it


def test_clips_are_cut_once_their_line_is_over(ring, clock):
    audio = CaptureAudio(ring)
    _play(ring, clock, 1)
    audio.add("1", at=clock.now, appeared=False)
    _play(ring, clock, capture_audio.AFTER_S - 1)
    assert audio.due() == []
    _play(ring, clock, 2)
    assert audio.due() == ["1"]
    audio.cut("1")
    assert audio.due() == []


def test_old_captures_lose_their_sound(ring, clock, monkeypatch):
    monkeypatch.setattr(capture_audio, "KEEP", 2)
    audio = CaptureAudio(ring)
    _play(ring, clock, 1)
    for capture_id in ("1", "2", "3"):
        audio.add(capture_id, at=clock.now, appeared=False)
    assert audio.cut("1") is None
    assert audio.cut("3") is not None
    assert audio.cut("unknown") is None
    assert audio.wav("1", 0, 1) is None


def test_wav_of_a_span(ring, clock):
    audio = CaptureAudio(ring)
    _play(ring, clock, 2, 0.5)
    audio.add("1", at=clock.now, appeared=False)
    with wave.open(io.BytesIO(audio.wav("1", 0.5, 1.5))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, RATE, RATE)
    with wave.open(io.BytesIO(audio.wav("1", 1.5, 99))) as wav:
        assert wav.getnframes() == RATE // 2  # up to the clip's end
