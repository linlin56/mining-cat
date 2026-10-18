"""Where a voiced line is in a recording of a game: around the moment its text appeared, or before the capture key was
pressed. Told from the loudness alone: it finds the voice over silence or quiet music, not over loud music, so it's only a
first guess, adjusted on the card creator's waveform."""
import numpy as np

FRAME_S = 0.02
# Quieter than this (RMS of samples in [-1, 1]) is silence, whatever the recording's own background.
SILENCE_RMS = 0.003
# A frame is voiced when it's this many times louder than the recording's quiet parts (its 20th percentile)...
FLOOR_RATIO = 3.0
FLOOR_PERCENTILE = 20
# ...pauses shorter than this are inside a line (between words or clauses), longer ones separate two lines...
MAX_PAUSE_S = 0.7
# ...and sounds shorter than this aren't a line (a click, a step).
MIN_VOICE_S = 0.15

# The text appears as the voice starts, give or take a game's delays.
APPEARED_BEFORE_S = 1.0
APPEARED_AFTER_S = 3.0
# The capture key is pressed during the line, or once it's over: not long after.
PRESSED_BEFORE_S = 10.0
# Without any voice found: the seconds after the text appeared, or before the key was pressed.
FALLBACK_S = 4.0


def voiced_spans(samples: np.ndarray, rate: int) -> list[tuple[float, float]]:
    """The loud parts of a mono recording, as (start, end) in seconds from its start, the short pauses inside them
    filled."""
    frame = max(1, round(rate * FRAME_S))
    count = len(samples) // frame
    if count == 0:
        return []
    frames = np.asarray(samples[:count * frame], dtype=np.float64).reshape(count, frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    threshold = max(SILENCE_RMS, float(np.percentile(rms, FLOOR_PERCENTILE)) * FLOOR_RATIO)
    spans: list[list[float]] = []
    for index in np.flatnonzero(rms > threshold):
        start, end = index * frame / rate, (index + 1) * frame / rate
        if spans and start - spans[-1][1] < MAX_PAUSE_S:
            spans[-1][1] = end
        else:
            spans.append([start, end])
    return [(start, end) for start, end in spans if end - start >= MIN_VOICE_S]


def line_span(spans: list[tuple[float, float]], anchor: float, appeared: bool, duration: float) -> tuple[float, float]:
    """The line among `spans` (from voiced_spans()), in a recording of `duration` seconds. `anchor` is when its text
    appeared (`appeared`), or when the capture key was pressed: the line is then the one going on, or the last one
    before."""
    if appeared:
        line = next((s for s in spans if s[1] > anchor - APPEARED_BEFORE_S and s[0] < anchor + APPEARED_AFTER_S), None)
        fallback = (anchor, anchor + FALLBACK_S)
    else:
        line = next((s for s in spans if s[0] <= anchor <= s[1]), None) or next(
            (s for s in reversed(spans) if anchor - PRESSED_BEFORE_S <= s[1] <= anchor), None)
        fallback = (anchor - FALLBACK_S, anchor)
    start, end = line or fallback
    return max(0.0, start), min(duration, end)
