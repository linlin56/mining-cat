"""Finding a sentence of a book in the subtitles of its audio: exactly, else roughly (subtitles transcribed by
Whisper don't always match the book's text word for word)."""
import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from difflib import SequenceMatcher

from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.subtitles.srt import Cue
from miningcat.domain.text.chinese_script import to_simplified

# Fuzzy matching (subtitles transcribed by Whisper don't always match the book's text word for word).
FUZZY_MIN_RATIO = 0.6

FUZZY_MAX_CUES = 3

_NOT_WORD = re.compile(r"[\W_]+", re.UNICODE)


@dataclass
class SubtitleTrack:
    """The cues of a subtitle file, and their text normalized for searching."""

    cues: list[Cue]
    text: str               # normalized text of all cues
    starts: list[int]       # where each cue begins in `text`


# Punctuation, spaces and case don't count; Chinese is compared in simplified characters
# (the subtitles may have been converted to the other script).
def normalize(text: str, language: str = "") -> str:
    text = _NOT_WORD.sub("", unicodedata.normalize("NFKC", text)).lower()
    if language in CHINESE_LANGUAGES:
        text = to_simplified(text)
    return text


def _span(track: SubtitleTrack, first: int, last: int) -> tuple[float, float]:
    return track.cues[first].start, track.cues[last].end


def _exact(track: SubtitleTrack, needle: str) -> tuple[float, float] | None:
    pos = track.text.find(needle)
    if pos < 0:
        return None
    first = bisect_right(track.starts, pos) - 1
    last = bisect_right(track.starts, pos + len(needle) - 1) - 1
    return _span(track, first, last)


def _fuzzy(track: SubtitleTrack, needle: str) -> tuple[float, tuple[float, float]] | None:
    best = None
    for first in range(len(track.cues)):
        for count in range(1, FUZZY_MAX_CUES + 1):
            last = first + count - 1
            if last >= len(track.cues):
                break
            end = track.starts[last + 1] if last + 1 < len(track.starts) else len(track.text)
            window = track.text[track.starts[first]:end]
            matcher = SequenceMatcher(None, needle, window, autojunk=False)
            if matcher.real_quick_ratio() < FUZZY_MIN_RATIO or matcher.quick_ratio() < FUZZY_MIN_RATIO:
                continue
            ratio = matcher.ratio()
            if ratio >= FUZZY_MIN_RATIO and (best is None or ratio > best[0]):
                best = (ratio, _span(track, first, last))
    return best



def track_of(cues: list[Cue], language: str = "") -> SubtitleTrack:
    text, starts = "", []
    for cue in cues:
        starts.append(len(text))
        text += normalize(cue.text, language)
    return SubtitleTrack(cues, text, starts)


def find(tracks: list[SubtitleTrack], needle: str, order: list[int]) -> tuple[int, tuple[float, float]] | None:
    """(track index, (start, end)) of a normalized sentence, the tracks tried in `order`: an exact match in any of
    them first, else the best rough match."""
    for i in order:
        span = _exact(tracks[i], needle)
        if span:
            return i, span
    best = None
    for i in order:
        result = _fuzzy(tracks[i], needle)
        if result and (best is None or result[0] > best[0]):
            best = (result[0], i, result[1])
            if result[0] > 0.9:
                break
    return (best[1], best[2]) if best else None
