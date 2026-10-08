import base64

from flask import Blueprint, jsonify, render_template, request, send_file

from web import profile, videos

bp = Blueprint("player", __name__, url_prefix="/player")

# Matroska is served as WebM: browsers that play Matroska only recognise that type.
_MIMETYPES = {"mkv": "video/webm", "webm": "video/webm", "mov": "video/mp4", "m4v": "video/mp4", "mp4": "video/mp4"}


@bp.errorhandler(videos.VideoError)
def _video_error(exc: videos.VideoError):
    return jsonify(title="Player", error=str(exc)), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.get("/")
@bp.get("/<video_id>")
def page(video_id: str | None = None):
    return render_template("player.html")


# ---------- library ----------

# Only the videos of the language studied (and those of no known language yet) are in the library.
@bp.get("/api/videos")
def api_videos():
    from miningcat.domain.languages import language_key

    study = profile.current()
    shown = [v for v in videos.list_videos() if not study or language_key(v["language"]) in (study, "")]
    return jsonify(videos=shown, downloads=videos.downloads(),
                   extensions=list(videos.VIDEO_EXTENSIONS), subtitle_extensions=list(videos.SUBTITLE_EXTENSIONS))


# The video is the request's body (not a form): it's written to the library as it arrives.
@bp.post("/api/videos")
def api_import():
    name = request.args.get("name") or ""
    # A video added while studying a language is in that language.
    study = profile.current()
    return jsonify(video=videos.import_stream(name, request.stream, language=profile.default_tag(study) if study else None))


@bp.post("/api/videos/url")
def api_import_url():
    import video_handlers
    from miningcat.domain.languages import Language

    body = _body()
    url = str(body.get("url") or "").strip()
    if not url:
        raise videos.VideoError("Enter a video URL.")
    try:
        video_handlers.get_handler(url)
    except ValueError:
        raise videos.VideoError("This site isn't supported: YouTube, Instagram (Reels) and Bilibili are.")
    try:
        language = Language.from_id(str(body.get("language"))) if body.get("language") else None
    except ValueError:
        raise videos.VideoError(f"Unknown language: {body.get('language')!r}")
    study = profile.current()
    return jsonify(job=videos.start_download(url, language, tag=profile.default_tag(study) if study else None))


@bp.post("/api/downloads/<job_id>/dismiss")
def api_dismiss_download(job_id: str):
    videos.dismiss_download(job_id)
    return jsonify(ok=True)


@bp.get("/api/videos/<video_id>")
def api_video(video_id: str):
    meta = videos.get_meta(video_id)
    return jsonify(video=meta, audio_tracks=videos.audio_tracks(meta),
                   progress=videos.get_progress(video_id), prefs=videos.get_prefs(video_id))


# Share of the words of the video's subtitles the user knows, and its recommended (i+1) lines
# (see mining/comprehension.py). Each subtitle line is a sentence, as in the subtitle list.
@bp.get("/api/videos/<video_id>/comprehension")
def api_comprehension(video_id: str):
    from mining import comprehension
    from miningcat.domain.languages import language_key

    meta = videos.get_meta(video_id)
    prefs = videos.get_prefs(video_id)
    language = language_key(prefs.get("language") or meta.get("language") or profile.default_tag(profile.current()))
    tracks = {t["id"]: t for t in meta.get("tracks", [])}
    track_id = prefs.get("primary") if "primary" in prefs else next(iter(tracks), "")
    if not language or track_id not in tracks:
        return jsonify(comprehension=None)
    path = videos._video_dir(video_id) / "comprehension.json"
    lines = lambda: [cue["text"].replace("\n", " ") for cue in videos.cues(video_id, track_id)]
    return jsonify(comprehension=comprehension.cached(path, language, [track_id, tracks[track_id].get("sha")], lines, whole=True))


@bp.get("/api/videos/<video_id>/file")
def api_file(video_id: str):
    path = videos.file_path(video_id)
    ext = path.suffix.lower().lstrip(".")
    return send_file(path, mimetype=_MIMETYPES.get(ext), conditional=True, max_age=0)


@bp.get("/api/videos/<video_id>/thumb")
def api_thumb(video_id: str):
    return send_file(videos.thumb_path(video_id), max_age=86400)


@bp.post("/api/videos/<video_id>/delete")
def api_delete(video_id: str):
    videos.delete_video(video_id)
    return jsonify(deleted=True)


# Prepares the video again: after another audio track was chosen, or with a `level` ("remux", "encode")
# when the browser can't play what it got.
@bp.post("/api/videos/<video_id>/prepare")
def api_prepare(video_id: str):
    videos.start_prepare(video_id, _body().get("level"))
    return jsonify(video=videos.get_meta(video_id))


# ---------- subtitles ----------

@bp.get("/api/videos/<video_id>/subtitles/<track_id>")
def api_cues(video_id: str, track_id: str):
    return jsonify(cues=videos.cues(video_id, track_id))


@bp.post("/api/videos/<video_id>/subtitles")
def api_add_subtitles(video_id: str):
    added, errors = [], []
    for upload in request.files.getlist("files"):
        name = upload.filename or "subtitles"
        try:
            added.append(videos.add_subtitles(video_id, name, upload.read()))
        except videos.VideoError as exc:
            errors.append(f"{name}: {exc}")
    return jsonify(added=added, errors=errors, tracks=videos.get_meta(video_id).get("tracks", []))


@bp.post("/api/videos/<video_id>/subtitles/<track_id>/delete")
def api_remove_subtitles(video_id: str, track_id: str):
    return jsonify(tracks=videos.remove_subtitles(video_id, track_id), prefs=videos.get_prefs(video_id))


# A subtitle's audio as MP3, as a data URL for the card creator's "Sentence audio". With `exact`, the span chosen on
# the waveform, without the settings' margins; `format` "wav" for the waveform itself.
@bp.post("/api/videos/<video_id>/clip")
def api_clip(video_id: str):
    body = _body()
    fmt = "wav" if body.get("format") == "wav" else "mp3"
    data = videos.clip(video_id, body.get("start"), body.get("end"), exact=bool(body.get("exact")), fmt=fmt)
    mime = "audio/wav" if fmt == "wav" else "audio/mpeg"
    return jsonify(data=f"data:{mime};base64," + base64.b64encode(data).decode("ascii"), name=f"sentence.{fmt}")


# A screenshot for the card creator, as a data URL.
@bp.post("/api/videos/<video_id>/frame")
def api_frame(video_id: str):
    data = videos.frame(video_id, _body().get("time"))
    return jsonify(data="data:image/jpeg;base64," + base64.b64encode(data).decode("ascii"), name="screenshot.jpg")


# ---------- progress, preferences, settings ----------

@bp.post("/api/videos/<video_id>/progress")
def api_progress(video_id: str):
    return jsonify(videos.save_progress(video_id, _body().get("time")))


@bp.post("/api/videos/<video_id>/prefs")
def api_prefs(video_id: str):
    return jsonify(videos.save_prefs(video_id, _body()))


@bp.get("/api/settings")
def api_get_settings():
    return jsonify(videos.get_settings())


@bp.post("/api/settings")
def api_save_settings():
    return jsonify(videos.save_settings(_body()))
