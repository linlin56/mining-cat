"""Timing a subtitle track on another one, of the same video in another language: the lines start at the same
moments (the same people speak), whatever they say. Only the start times are compared.

The timing found maps the track's times to the video's: video = scale × track + offset. The scale corrects a
track made for another frame rate (a 25 fps PAL release against a 23.976 fps Blu-ray)."""
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass
from statistics import median

# 1, then the usual frame-rate conversions, both ways
SCALES = (1.0, 25 / (24000 / 1001), (24000 / 1001) / 25, 25 / 24, 24 / 25, 24 / (24000 / 1001), (24000 / 1001) / 24)
MAX_OFFSET_S = 600
TOLERANCE_S = 0.25   # a line starts "at the same time" as the reference's within this
_BIN_S = 0.1
_CANDIDATES = 12     # most common start differences tried, for each scale
MIN_MATCHED = 0.3    # share of the lines that must find their reference line, else no alignment


@dataclass(frozen=True)
class Timing:
    offset: float
    scale: float
    matched: int     # lines starting with a reference line, once aligned
    lines: int


def _matches(reference: list[float], starts: list[float], scale: float, offset: float) -> list[tuple[float, float]]:
    """(line start, reference start) of each line starting within the tolerance of a reference line."""
    pairs = []
    for t in starts:
        moved = scale * t + offset
        i = bisect_left(reference, moved)
        near = min((reference[j] for j in (i - 1, i) if 0 <= j < len(reference)), key=lambda r: abs(r - moved))
        if abs(near - moved) <= TOLERANCE_S:
            pairs.append((t, near))
    return pairs


def align(reference: list[float], starts: list[float]) -> Timing | None:
    """The timing of the lines starting at `starts` on the lines starting at `reference`, or None if they don't
    match (another episode, or too few lines alike)."""
    reference = sorted(reference)
    starts = sorted(starts)
    if not reference or not starts:
        return None
    best: tuple[int, float, float] | None = None
    for scale in SCALES:
        # the offset that makes most lines start together is among the most common start differences
        bins = Counter(round((r - scale * t) / _BIN_S) for t in starts for r in reference
                       if abs(r - scale * t) <= MAX_OFFSET_S)
        for b, _ in bins.most_common(_CANDIDATES):
            offset = b * _BIN_S
            pairs = _matches(reference, starts, scale, offset)
            if not pairs:
                continue
            offset = median(r - scale * t for t, r in pairs)  # refined on the lines that match
            matched = len(_matches(reference, starts, scale, offset))
            # a scale other than 1 must do clearly better: else it's chance
            if best is None or matched > best[0] * (1.0 if scale == 1.0 else 1.1):
                best = (matched, scale, offset)
    if best is None or best[0] < MIN_MATCHED * len(starts):
        return None
    matched, scale, offset = best
    return Timing(round(offset, 3), scale, matched, len(starts))
