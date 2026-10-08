import json
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from web import books

AUDIO_DIR_NAME = "audio"
# A little silence around a cut sentence, so that its first and last sounds aren't clipped.
CLIP_PADDING_S = 0.15
# Fuzzy matching (subtitles transcribed by Whisper don't always match the book's text word for word).
FUZZY_MIN_RATIO = 0.6
FUZZY_MAX_CUES = 3

_TIMESTAMP = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})")
_NOT_WORD = re.compile(r"[\W_]+", re.UNICODE)


class AudioError(Exception):
    pass


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_srt(text: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            m = _TIMESTAMP.search(line)
            if m:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(v) for v in m.groups())
                cue_text = " ".join(l.strip() for l in lines[i + 1:] if l.strip())
                cue_text = re.sub(r"<[^>]+>", "", cue_text)
                cues.append(Cue(h1 * 3600 + m1 * 60 + s1 + ms1 / 1000, h2 * 3600 + m2 * 60 + s2 + ms2 / 1000, cue_text))
                break
    return cues


def _audio_dir(book_id: str) -> Path:
    return books._book_dir(book_id) / AUDIO_DIR_NAME


def info(book_id: str) -> dict | None:
    data = books._read_json(_audio_dir(book_id) / "audio.json", None)
    if not data:
        return None
    return {"tracks": len(data["tracks"]), "linked": data.get("linked"), "names": [t["name"] for t in data["tracks"]]}


# Pairs every chapter audio file with the subtitles of the same name.
def output_tracks(audio_dir: Path, srt_dir: Path) -> list[tuple[Path, Path]]:
    from config import glob_audio_files
    pairs = []
    for audio in glob_audio_files(audio_dir):
        srt = srt_dir / f"{audio.stem}.srt"
        if srt.is_file():
            pairs.append((audio, srt))
    return pairs


def attach(book_id: str, pairs: list[tuple[Path, Path]]) -> dict:
    """Copies the (audio, subtitles) pairs into the book's folder, replacing any previous audio."""
    if not pairs:
        raise AudioError("No converted audio found: run a conversion with this book first "
                         "(Audiobook / Ebook, Standard or Generate audio mode).")
    books.get_meta(book_id)
    folder = _audio_dir(book_id)
    tmp = folder.with_name(AUDIO_DIR_NAME + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    tracks = []
    for i, (audio, srt) in enumerate(pairs, start=1):
        name = f"{i:03d}"
        shutil.copy2(audio, tmp / f"{name}{audio.suffix.lower()}")
        shutil.copy2(srt, tmp / f"{name}.srt")
        tracks.append({"audio": f"{name}{audio.suffix.lower()}", "srt": f"{name}.srt", "name": audio.stem})
    (tmp / "audio.json").write_text(json.dumps({"tracks": tracks, "linked": time.time()}, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(folder, ignore_errors=True)
    tmp.replace(folder)
    _forget(book_id)
    return info(book_id)


def attach_from_output(book_id: str) -> dict:
    from config import DIR_CHAPTERS_AUDIO, DIR_SRT
    return attach(book_id, output_tracks(DIR_CHAPTERS_AUDIO, DIR_SRT))


def remove(book_id: str) -> None:
    shutil.rmtree(_audio_dir(book_id), ignore_errors=True)
    _forget(book_id)


def track_path(book_id: str, track: int) -> Path:
    data = books._read_json(_audio_dir(book_id) / "audio.json", None)
    if not data or not 0 <= track < len(data["tracks"]):
        raise AudioError("No such audio track.")
    return _audio_dir(book_id) / data["tracks"][track]["audio"]


# ---------------------------------------------------------------- finding a sentence

@dataclass
class _Track:
    cues: list[Cue]
    text: str               # normalized text of all cues
    starts: list[int]       # where each cue begins in `text`


_index: dict[str, tuple[float, list[_Track]]] = {}
_index_lock = threading.Lock()
# Track where the sentences of a reader chapter were found last: (book, chapter) -> track
_chapter_track: dict[tuple[str, int], int] = {}


def _forget(book_id: str) -> None:
    with _index_lock:
        _index.pop(book_id, None)
        for key in [k for k in _chapter_track if k[0] == book_id]:
            del _chapter_track[key]


# Punctuation, spaces and case don't count; Chinese is compared in simplified characters
# (the subtitles may have been converted to the other script).
def normalize(text: str, language: str = "") -> str:
    text = _NOT_WORD.sub("", unicodedata.normalize("NFKC", text)).lower()
    if language in ("zh", "yue", "nan"):
        from miningcat.domain.text.chinese_script import to_simplified
        text = to_simplified(text)
    return text


def _tracks(book_id: str, language: str) -> list[_Track]:
    path = _audio_dir(book_id) / "audio.json"
    if not path.exists():
        raise AudioError("This book has no audio.")
    mtime = path.stat().st_mtime
    with _index_lock:
        cached = _index.get(book_id)
        if cached and cached[0] == mtime:
            return cached[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    tracks = []
    for t in data["tracks"]:
        cues = parse_srt((_audio_dir(book_id) / t["srt"]).read_text(encoding="utf-8", errors="replace"))
        text, starts = "", []
        for cue in cues:
            starts.append(len(text))
            text += normalize(cue.text, language)
        tracks.append(_Track(cues, text, starts))
    with _index_lock:
        _index[book_id] = (mtime, tracks)
    return tracks


def _span(track: _Track, first: int, last: int) -> tuple[float, float]:
    return track.cues[first].start, track.cues[last].end


def _exact(track: _Track, needle: str) -> tuple[float, float] | None:
    pos = track.text.find(needle)
    if pos < 0:
        return None
    first = bisect_right(track.starts, pos) - 1
    last = bisect_right(track.starts, pos + len(needle) - 1) - 1
    return _span(track, first, last)


def _fuzzy(track: _Track, needle: str) -> tuple[float, tuple[float, float]] | None:
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


def find_sentence(book_id: str, sentence: str, chapter: int | None = None, language: str = "") -> dict | None:
    """Time span of `sentence` in the book's audio: {"track", "start", "end"}, or None if it can't be found."""
    needle = normalize(sentence, language)
    if not needle:
        return None
    tracks = _tracks(book_id, language)
    preferred = _chapter_track.get((book_id, chapter))
    order = list(range(len(tracks)))
    if preferred is not None and preferred < len(tracks):
        order.remove(preferred)
        order.insert(0, preferred)

    found = None
    for i in order:
        span = _exact(tracks[i], needle)
        if span:
            found = (i, span)
            break
    if found is None:
        best = None
        for i in order:
            result = _fuzzy(tracks[i], needle)
            if result and (best is None or result[0] > best[0]):
                best = (result[0], i, result[1])
                if result[0] > 0.9:
                    break
        if best:
            found = (best[1], best[2])
    if found is None:
        return None
    track, (start, end) = found
    if chapter is not None:
        _chapter_track[(book_id, chapter)] = track
    return {"track": track, "start": round(start, 3), "end": round(end, 3)}


def clip(book_id: str, track: int, start: float, end: float) -> bytes:
    return cut_mp3(track_path(book_id, track), start, end)


# MP3 for cards; WAV (16 kHz, 16 bits) for the card creator's waveform: decoded exactly, with no encoder delay.
_CODECS = {"mp3": ["-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3"],
           "wav": ["-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav"]}


def cut_mp3(source: Path, start: float, end: float, audio_stream: int = 0,
            before: float = CLIP_PADDING_S, after: float = CLIP_PADDING_S, fmt: str = "mp3") -> bytes:
    """The span of an audio (or video) file as MP3 (or WAV), cut with ffmpeg. Constant bitrate: written to a pipe, a
    variable bitrate MP3 has no header giving its length, and players would show a wrong duration."""
    start = max(0.0, float(start) - before)
    end = float(end) + after
    if end <= start:
        raise AudioError("Invalid time span.")
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
             "-i", str(source), "-map", f"0:a:{audio_stream}", "-vn", "-ac", "1", *_CODECS[fmt], "pipe:1"],
            capture_output=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        raise AudioError("ffmpeg isn't installed: it's needed to cut the sentence's audio.")
    except subprocess.CalledProcessError as exc:
        raise AudioError(f"ffmpeg couldn't cut the audio: {exc.stderr.decode(errors='replace').strip()[:300]}")
    except subprocess.TimeoutExpired:
        raise AudioError("ffmpeg took too long to cut the audio.")
    return result.stdout
