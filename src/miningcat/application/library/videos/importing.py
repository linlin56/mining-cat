"""Videos imported into the player's library: uploaded, or already on disk (downloads, conversions)."""
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from miningcat.application.library.videos import store
from miningcat.application.library.videos.preparation import get_meta, start_prepare
from miningcat.application.library.videos.subtitles import add_subtitles
from miningcat.domain.library.errors import VideoError
from miningcat.infrastructure.files.json_files import write_json

VIDEO_EXTENSIONS = ("mp4", "mkv", "webm", "mov", "m4v", "avi", "ts", "flv", "wmv", "mpg", "mpeg")

# A video's id comes from its size and its first and last bytes: hashing a whole movie would take too long.
FINGERPRINT_BYTES = 4 * 1024 * 1024


def fingerprint(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as f:
        digest.update(f.read(FINGERPRINT_BYTES))
        if size > FINGERPRINT_BYTES:
            f.seek(max(FINGERPRINT_BYTES, size - FINGERPRINT_BYTES))
            digest.update(f.read())
    return digest.hexdigest()[:16]


def _extension(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in VIDEO_EXTENSIONS:
        raise VideoError(f"Unsupported format: .{ext or '?'} (supported: {', '.join(VIDEO_EXTENSIONS)})")
    return ext


def import_stream(filename: str, stream, language: str | None = None) -> dict:
    """Imports an uploaded video, written straight to the library as it arrives (a movie doesn't fit in memory)."""
    ext = _extension(filename)
    store.videos_dir().mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".upload-", suffix=f".{ext}", dir=store.videos_dir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(stream, out, 1024 * 1024)
        if tmp.stat().st_size == 0:
            raise VideoError("The file is empty.")
        return _add(tmp, ext, Path(filename).name, move=True, language=language)
    finally:
        tmp.unlink(missing_ok=True)


def import_file(path: Path, title: str | None = None, language: str | None = None,
                subtitles: list[tuple[Path, str]] = ()) -> dict:
    """Imports a video already on disk (a download, a conversion), hard-linked when possible.
    `subtitles`: (file, label) pairs, e.g. the captions downloaded with an online video."""
    meta = _add(path, _extension(path.name), path.name, move=False, title=title, language=language)
    for sub, label in subtitles:
        try:
            add_subtitles(meta["id"], sub.name, sub.read_bytes(), origin="platform", label=label)
        except (VideoError, OSError):
            pass  # a broken caption file mustn't lose the video
    return get_meta(meta["id"])


def _link_or_copy(source: Path, target: Path) -> None:
    """A hard link (no copy of a whole movie) when the file is on the same disk."""
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _add(file: Path, ext: str, filename: str, move: bool, title: str | None = None, language: str | None = None) -> dict:
    video_id = fingerprint(file)
    folder = store.video_folder(video_id)
    with store.lock:
        if (folder / "meta.json").exists():
            return get_meta(video_id)
        shutil.rmtree(folder, ignore_errors=True)  # leftovers of an interrupted import
        folder.mkdir(parents=True)
        target = folder / f"source.{ext}"
        if move:
            file.replace(target)
        else:
            _link_or_copy(file, target)
        if language:
            write_json(folder / "prefs.json", {"language": language})
        write_json(folder / "meta.json", {
            "id": video_id, "filename": filename, "title": title or Path(filename).stem,
            "added": time.time(), "status": "queued", "progress": 0, "error": None, "tracks": [],
        })
        start_prepare(video_id)
    return get_meta(video_id)
