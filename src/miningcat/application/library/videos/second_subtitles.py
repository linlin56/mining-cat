"""Second subtitles: a subtitle track of a video translated to the language of the settings, in the background, added
as a new track and shown under the subtitles."""
from miningcat.application.library.videos import store
from miningcat.application.library.videos.subtitles import add_subtitles, subtitle_path
from miningcat.application.mining import translation
from miningcat.domain.library.errors import VideoError
from miningcat.domain.languages import LANGUAGES


class SubtitleTranslations:
    """The translation of each video's subtitles: {"state" (idle, running, done, error), "done", "total", "target",
    "model" (its name), "error", "track" (the new track)}."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def state(self, video_id: str) -> dict:
        return dict(self._jobs.get(video_id, {"state": "idle"}))

    def start(self, video_id: str, track_id: str, language: str) -> dict:
        """Translates a track of the video from `language` (a study language: "zh", "ja"...)."""
        target = translation.check(language)
        path = subtitle_path(video_id, track_id)
        with store.lock:
            if self.state(video_id)["state"] == "running":
                raise VideoError("These subtitles are already being translated.")
            self._jobs[video_id] = {"state": "running", "done": 0, "total": 0, "target": LANGUAGES[target],
                                    "model": translation.model_label(), "error": None, "track": None}
        store.spawn(self._run, video_id, path, language, target)
        return self.state(video_id)

    def _run(self, video_id: str, path, language: str, target: str) -> None:
        job = self._jobs[video_id]
        try:
            srt = path.read_text(encoding="utf-8", errors="replace")
            translated = translation.translate_srt(language, srt, lambda done, total: job.update(done=done, total=total))
            track = add_subtitles(video_id, f"{target}.srt", translated.encode("utf-8"), origin="translation",
                                  label=f"{LANGUAGES[target]} (translated)")
            with store.lock:
                prefs = store.read_file(video_id, "prefs.json", {})
                store.write_file(video_id, "prefs.json", {**prefs, "secondary": track["id"]})
            job.update(state="done", track=track)
        except Exception as exc:
            job.update(state="error", error=str(exc))


_translations = SubtitleTranslations()


def start_translation(video_id: str, track_id: str, language: str) -> dict:
    return _translations.start(video_id, track_id, language)


def translation_state(video_id: str) -> dict:
    return _translations.state(video_id)
