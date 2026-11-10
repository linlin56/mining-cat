import random

from miningcat.domain.subtitles.alignment import align

# The lines of an episode: they start every 2 to 6 s.
_rng = random.Random(4)
REFERENCE = []
for _ in range(300):
    REFERENCE.append(round((REFERENCE[-1] if REFERENCE else 10) + _rng.uniform(2, 6), 2))


def other_track(shift=0.0, scale=1.0, keep=0.9, jitter=0.08, seed=1):
    """The same episode subtitled by others: some lines split or merged (missing here), timed a little differently."""
    rng = random.Random(seed)
    return [(t - shift) / scale + rng.uniform(-jitter, jitter) for t in REFERENCE if rng.random() < keep]


def test_finds_the_offset():
    timing = align(REFERENCE, other_track(shift=8.02))
    assert abs(timing.offset - 8.02) < 0.05 and timing.scale == 1.0
    assert timing.matched >= 0.95 * timing.lines


def test_late_track_and_extra_lines():
    rng = random.Random(2)
    starts = other_track(shift=-42.5) + [rng.uniform(0, 1400) for _ in range(40)]  # songs, signs: lines of its own
    timing = align(REFERENCE, starts)
    assert abs(timing.offset + 42.5) < 0.05 and timing.scale == 1.0


def test_finds_another_frame_rate():
    pal = 25 / (24000 / 1001)  # a 25 fps release runs 4 % faster
    timing = align(REFERENCE, other_track(shift=3.0, scale=pal))
    assert abs(timing.scale - pal) < 1e-9 and abs(timing.offset - 3.0) < 0.1


def test_same_track():
    timing = align(REFERENCE, REFERENCE)
    assert (timing.offset, timing.scale, timing.matched, timing.lines) == (0.0, 1.0, 300, 300)


def test_no_match():
    rng = random.Random(3)
    assert align(REFERENCE, sorted(rng.uniform(0, 1400) for _ in range(300))) is None
    assert align(REFERENCE, []) is None and align([], REFERENCE) is None
