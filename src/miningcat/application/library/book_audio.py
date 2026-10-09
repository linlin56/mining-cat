"""The audio of a converted book: the chapters' audio and subtitles (output/chapters_audio + output/srt), copied next
to the book. A sentence of the reader is found in the subtitles, then played, or cut for the card creator."""
import json
import shutil
import threading
import time
from pathlib import Path

from miningcat.application.library.books import book_folder, get_meta
from miningcat.config.paths import paths
from miningcat.domain.library.errors import AudioError
from miningcat.domain.subtitles import sentence_search
from miningcat.domain.subtitles.sentence_search import SubtitleTrack
from miningcat.domain.subtitles.srt import parse_srt
from miningcat.infrastructure.files.json_files import read_json
from miningcat.infrastructure.media.audio_clip import cut_mp3
from miningcat.infrastructure.media.audio_files import glob_audio_files

AUDIO_DIR_NAME = "audio"


def _audio_dir(book_id: str) -> Path:
    return book_folder(book_id) / AUDIO_DIR_NAME


class _SubtitleIndex:
    """The searchable subtitles of each book (until its audio changes), and the track where the sentences of each
    reader chapter were found last (tried first next time)."""

    def __init__(self):
        self._tracks: dict[str, tuple[float, list[SubtitleTrack]]] = {}
        self.chapter_track: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def forget(self, book_id: str) -> None:
        with self._lock:
            self._tracks.pop(book_id, None)
            for key in [k for k in self.chapter_track if k[0] == book_id]:
                del self.chapter_track[key]

    def tracks(self, book_id: str, language: str) -> list[SubtitleTrack]:
        path = _audio_dir(book_id) / "audio.json"
        if not path.exists():
            raise AudioError("This book has no audio.")
        mtime = path.stat().st_mtime
        with self._lock:
            cached = self._tracks.get(book_id)
            if cached and cached[0] == mtime:
                return cached[1]
        data = json.loads(path.read_text(encoding="utf-8"))
        tracks = [
            sentence_search.track_of(parse_srt((_audio_dir(book_id) / t["srt"]).read_text(encoding="utf-8", errors="replace")),
                                     language)
            for t in data["tracks"]
        ]
        with self._lock:
            self._tracks[book_id] = (mtime, tracks)
        return tracks


_index = _SubtitleIndex()


def info(book_id: str) -> dict | None:
    data = read_json(_audio_dir(book_id) / "audio.json", None)
    if not data:
        return None
    return {"tracks": len(data["tracks"]), "linked": data.get("linked"), "names": [t["name"] for t in data["tracks"]]}


def output_tracks(audio_dir: Path, srt_dir: Path) -> list[tuple[Path, Path]]:
    """Every chapter audio file paired with the subtitles of the same name."""
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
    get_meta(book_id)
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
    (tmp / "audio.json").write_text(json.dumps({"tracks": tracks, "linked": time.time()}, ensure_ascii=False),
                                    encoding="utf-8")
    shutil.rmtree(folder, ignore_errors=True)
    tmp.replace(folder)
    _index.forget(book_id)
    return info(book_id)


def attach_from_output(book_id: str) -> dict:
    """Attaches the audio of the last conversion."""
    return attach(book_id, output_tracks(paths.chapters_audio, paths.srt))


def remove(book_id: str) -> None:
    shutil.rmtree(_audio_dir(book_id), ignore_errors=True)
    _index.forget(book_id)


def track_path(book_id: str, track: int) -> Path:
    data = read_json(_audio_dir(book_id) / "audio.json", None)
    if not data or not 0 <= track < len(data["tracks"]):
        raise AudioError("No such audio track.")
    return _audio_dir(book_id) / data["tracks"][track]["audio"]


def find_sentence(book_id: str, sentence: str, chapter: int | None = None, language: str = "") -> dict | None:
    """Time span of `sentence` in the book's audio: {"track", "start", "end"}, or None if it can't be found."""
    needle = sentence_search.normalize(sentence, language)
    if not needle:
        return None
    tracks = _index.tracks(book_id, language)
    preferred = _index.chapter_track.get((book_id, chapter))
    order = list(range(len(tracks)))
    if preferred is not None and preferred < len(tracks):
        order.remove(preferred)
        order.insert(0, preferred)
    found = sentence_search.find(tracks, needle, order)
    if found is None:
        return None
    track, (start, end) = found
    if chapter is not None:
        _index.chapter_track[(book_id, chapter)] = track
    return {"track": track, "start": round(start, 3), "end": round(end, 3)}


def clip(book_id: str, track: int, start: float, end: float) -> bytes:
    return cut_mp3(track_path(book_id, track), start, end)
