import numpy as np
import pytest

from miningcat.domain.audio.voice import line_span, voiced_spans

RATE = 16000


def _recording(*parts):
    """Silence and tones, e.g. (1.0, 0) then (2.0, 0.3): seconds and loudness."""
    rng = np.random.default_rng(0)
    chunks = []
    for seconds, loudness in parts:
        t = np.arange(round(seconds * RATE)) / RATE
        chunks.append(loudness * np.sin(2 * np.pi * 220 * t) + rng.normal(0, 0.0005, len(t)))
    return np.concatenate(chunks).astype(np.float32)


def _close(span, expected):
    assert span == pytest.approx(expected, abs=0.05)


def test_voice_over_silence():
    spans = voiced_spans(_recording((1.0, 0), (2.0, 0.3), (1.5, 0), (1.0, 0.3), (1.0, 0)), RATE)
    assert len(spans) == 2
    _close(spans[0], (1.0, 3.0))
    _close(spans[1], (4.5, 5.5))


def test_short_pauses_are_inside_a_line_and_clicks_are_not_lines():
    spans = voiced_spans(_recording((1.0, 0), (1.0, 0.3), (0.3, 0), (1.0, 0.3), (1.0, 0), (0.05, 0.5), (1.0, 0)), RATE)
    assert len(spans) == 1
    _close(spans[0], (1.0, 3.3))


def test_voice_over_quiet_music():
    music = 0.01
    spans = voiced_spans(_recording((2.0, music), (2.0, 0.3), (2.0, music)), RATE)
    assert len(spans) == 1
    _close(spans[0], (2.0, 4.0))


def test_silence_has_no_voice():
    assert voiced_spans(_recording((3.0, 0)), RATE) == []
    assert voiced_spans(np.zeros(0, dtype=np.float32), RATE) == []


SPANS = [(1.0, 3.0), (5.0, 8.0), (12.0, 13.0)]


def test_line_starting_as_its_text_appears():
    assert line_span(SPANS, 4.6, appeared=True, duration=20) == (5.0, 8.0)
    # the voice started a little before the text was drawn
    assert line_span(SPANS, 5.5, appeared=True, duration=20) == (5.0, 8.0)


def test_text_appearing_without_voice_takes_the_seconds_after_it():
    assert line_span(SPANS, 9.0, appeared=True, duration=20) == (9.0, 13.0)
    assert line_span([], 18.0, appeared=True, duration=20) == (18.0, 20)


def test_key_pressed_during_a_line_or_after_it():
    assert line_span(SPANS, 6.0, appeared=False, duration=20) == (5.0, 8.0)
    assert line_span(SPANS, 10.0, appeared=False, duration=20) == (5.0, 8.0)


def test_key_pressed_long_after_any_voice_takes_the_seconds_before():
    assert line_span(SPANS, 30.0, appeared=False, duration=40) == (26.0, 30.0)
    assert line_span([], 2.0, appeared=False, duration=20) == (0.0, 2.0)
