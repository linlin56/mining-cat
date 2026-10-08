"""The files of the converter page: uploads, the chapters of a book, the tracks of a video, previews for the OCR."""
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from miningcat.application.converter import options, source_files
from miningcat.application.converter.video_download import download_video
from miningcat.config.paths import paths
from miningcat.infrastructure.media import video_frames
from miningcat.infrastructure.media.audio_files import AUDIO_EXTENSIONS
from miningcat.infrastructure.media.video_file import list_audio_tracks
from miningcat.interfaces.web import uploads
from miningcat.interfaces.web.blueprints.converter import refs
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import current_state
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("converter_files", __name__)

_EXTENSIONS = {"audio": AUDIO_EXTENSIONS, "ebook": options.EBOOK_EXTENSIONS, "video": options.VIDEO_EXTENSIONS}


@bp.post("/api/upload/<kind>")
def api_upload(kind: str):
    extensions = _EXTENSIONS.get(kind)
    if extensions is None:
        raise UserError("Upload failed", f"Unknown file kind: {kind}", 404)
    saved, rejected = uploads.save_uploads(kind, request.files.getlist("files"), extensions)
    return jsonify(files=saved, rejected=rejected)


@bp.post("/api/discard")
def api_discard():
    try:
        removed = uploads.discard(json_body().get("path"))
    except uploads.InvalidPathError as exc:
        raise UserError("File not available", str(exc))
    return jsonify(removed=removed)


@bp.post("/api/chapters")
def api_chapters():
    files = source_files.normalize_ebook_selection(refs(json_body().get("files")))
    try:
        chapters = source_files.load_chapters(files)
        error = None
    except Exception as exc:
        chapters, error = [], f"Could not read the book: {exc}"
    return jsonify(
        files=[uploads.describe(p) for p in files],
        chapters=[{"index": i, "title": title} for i, (title, _) in enumerate(chapters)],
        error=error,
    )


@bp.post("/api/video/tracks")
def api_video_tracks():
    video_file = refs([json_body().get("path")])[0]
    try:
        tracks = list_audio_tracks(video_file)
    except Exception:
        tracks = []
    return jsonify(tracks=[{"index": t["index"], "label": options.audio_track_label(t)} for t in tracks])


@bp.post("/api/video/validate")
def api_video_validate():
    body = json_body()
    return jsonify(error=options.validate_video_url(str(body.get("url") or "").strip(), body.get("website")))


# Grabs a carousel of candidate frames for the subtitle region picker. For a URL the video is
# downloaded first (yt-dlp then skips re-downloading it when the video is generated).
@bp.post("/api/ocr/preview")
def api_ocr_preview():
    body = json_body()
    if body.get("path"):
        video_file = refs([body["path"]])[0]
    else:
        url = str(body.get("url") or "").strip()
        if not url:
            raise UserError("Missing URL", "Enter a video URL.")
        try:
            video_file = download_video(url, paths.videos, app_id="web")
        except Exception as exc:
            raise UserError("Download failed", f"Could not download the video for preview:\n{exc}")
    try:
        preview_paths = video_frames.grab_sample_frames(video_file, paths.temp / "ocr_region_preview")
        width, height = video_frames.probe_dimensions(video_file)
    except Exception as exc:
        raise UserError("Preview failed", f"Could not load preview frames:\n{exc}")
    preview = current_state().ocr_preview
    preview["frames"] = [Path(p) for p in preview_paths]
    preview["version"] += 1
    return jsonify(
        width=width, height=height,
        frames=[f"/api/ocr/frame/{i}?v={preview['version']}" for i in range(len(preview_paths))],
    )


@bp.get("/api/ocr/frame/<int:index>")
def api_ocr_frame(index: int):
    frame_list = current_state().ocr_preview["frames"]
    if not 0 <= index < len(frame_list) or not frame_list[index].is_file():
        return jsonify(error="Frame not found"), 404
    return send_file(frame_list[index], mimetype="image/jpeg", max_age=0)
