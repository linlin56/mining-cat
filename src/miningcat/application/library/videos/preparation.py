"""Videos prepared once, in the background: ffprobe, embedded subtitles, thumbnail, and a copy for the browser
only when it can't play the original (a remux into MP4 first, a re-encode when it can't decode the codec)."""
import subprocess
import threading

from miningcat.application.converter.options import audio_track_label
from miningcat.application.library.videos import store
from miningcat.application.library.videos.subtitles import add_embedded_subtitles, cues
from miningcat.domain.library.errors import VideoError
from miningcat.domain.text.language_detection import detect_language
from miningcat.infrastructure.media.browser_video import LEVELS, play_plan, probe, thumbnail, transcode


class VideoPreparation:
    """Prepares one video at a time (ffmpeg uses the whole machine), each video once at a time."""

    def __init__(self):
        self._preparing: set[str] = set()
        self._work_lock = threading.Lock()

    def is_preparing(self, video_id: str) -> bool:
        return video_id in self._preparing

    def start(self, video_id: str, level: str | None = None) -> None:
        """Prepares the video (again). `level`: see play_plan(); by default, the one the video already needed."""
        if level is not None and level not in LEVELS:
            raise VideoError(f"Unknown preparation: {level!r}")
        with store.lock:
            if video_id in self._preparing:
                raise VideoError("This video is already being prepared.")
            self._preparing.add(video_id)
            try:
                store.update_meta(video_id, status="queued", progress=0, error=None, eta=None)
            except VideoError:
                self._preparing.discard(video_id)
                raise
        store.spawn(self._prepare, video_id, level)

    def _prepare(self, video_id: str, level: str | None = None) -> None:
        try:
            with self._work_lock:
                self._run(video_id, level)
        except (VideoError, OSError, subprocess.SubprocessError) as exc:
            try:
                store.update_meta(video_id, status="error", error=str(exc))
            except (VideoError, OSError):
                pass  # deleted in the meantime
        finally:
            self._preparing.discard(video_id)

    @staticmethod
    def _run(video_id: str, level: str | None) -> None:
        folder = store.video_folder(video_id)
        source = store.source_file(folder)
        meta = store.update_meta(video_id, status="preparing", progress=0, step="reading")
        level = level or meta.get("level") or "auto"
        info = probe(source)
        if not meta.get("probed"):
            store.update_meta(video_id, **info, step="subtitles")
            add_embedded_subtitles(video_id, source)
            if info["video_codec"]:
                store.update_meta(video_id, step="thumbnail")
                thumbnail(source, folder / "thumb.jpg", info["duration"])
            meta = store.update_meta(video_id, probed=True)
        audio_track = store.read_file(video_id, "prefs.json", {}).get("audio_track", 0)
        plan = play_plan(source.suffix.lower().lstrip("."), info, audio_track, level)
        play = folder / "play.mp4"
        if plan is None:
            play.unlink(missing_ok=True)
        elif not (play.exists() and meta.get("play_plan") == plan):
            store.update_meta(video_id, step="encoding" if plan["video"] == "h264" else "remuxing")

            def started(proc: subprocess.Popen) -> None:
                store.processes[video_id] = proc

            try:
                transcode(source, play, plan, info["duration"], on_start=started,
                          on_progress=lambda percent, eta: store.update_meta(video_id, progress=percent, eta=eta))
            finally:
                store.processes.pop(video_id, None)
        if not meta.get("language"):
            meta = store.update_meta(video_id, language=_detect_language(video_id, meta))
        store.update_meta(video_id, status="ready", progress=100, error=None, eta=None, step=None, play_plan=plan,
                          level=level)


def _detect_language(video_id: str, meta: dict) -> str | None:
    """The language of the video's subtitles."""
    for track in meta.get("tracks", []):
        language = detect_language(" ".join(c["text"] for c in cues(video_id, track["id"])[:400]))
        if language:
            return language
    return None


preparation = VideoPreparation()


def start_prepare(video_id: str, level: str | None = None) -> None:
    preparation.start(video_id, level)


def get_meta(video_id: str) -> dict:
    """The metadata of a video. A preparation interrupted by a restart of MiningCat is started again."""
    with store.lock:
        meta = store.read_meta(video_id)
        if meta.get("status") in ("queued", "preparing") and not preparation.is_preparing(video_id):
            start_prepare(video_id)
            meta = store.read_file(video_id, "meta.json", meta)
        return meta


def audio_tracks(meta: dict) -> list[dict]:
    return [{"index": t["index"], "label": audio_track_label(t)} for t in meta.get("audio", [])]
