"""Online videos downloaded with the converter's platform handlers (YouTube captions included), then imported."""
import secrets

from miningcat.application.converter.video_download import download_video
from miningcat.application.library.videos import store
from miningcat.application.library.videos.importing import import_file
from miningcat.config.paths import paths
from miningcat.infrastructure.downloads.handler import BASE_YDL_OPTS
from miningcat.infrastructure.media.video_file import find_platform_subtitles, sidecar_tag

_downloads: dict[str, dict] = {}


def start_download(url: str, language, tag: str | None = None) -> dict:
    """Downloads an online video with the converter's platform handlers (YouTube captions included), then imports it."""
    job = {"id": secrets.token_hex(6), "url": url, "status": "downloading", "error": None, "video": None}
    _downloads[job["id"]] = job
    started = dict(job)
    store.spawn(_download, job, language, tag)
    return started


def _online_title(url: str) -> str | None:
    try:
        import yt_dlp

        with yt_dlp.YoutubeDL(BASE_YDL_OPTS) as ydl:
            return ydl.extract_info(url, download=False).get("title")
    except Exception:
        return None


# `tag`: the video's language tag when `language` (the converter's, for YouTube captions) isn't given.
def _download(job: dict, language, tag: str | None = None) -> None:
    try:
        path = download_video(job["url"], paths.videos, app_id="web", language=language)
        subtitles = [(p, sidecar_tag(p, path.stem)) for p in find_platform_subtitles(path.parent, path.stem)]
        meta = import_file(path, title=_online_title(job["url"]), language=language.profile.tag if language else tag,
                           subtitles=subtitles)
        job.update(status="done", video=meta["id"])
    except Exception as exc:
        job.update(status="error", error=str(exc) or type(exc).__name__)


def downloads() -> list[dict]:
    return [dict(j) for j in _downloads.values() if j["status"] != "done"]


def dismiss_download(job_id: str) -> None:
    job = _downloads.get(job_id)
    if job and job["status"] != "downloading":
        del _downloads[job_id]
