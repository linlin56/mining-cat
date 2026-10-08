"""The converter's jobs: options, starting a conversion, and following it."""
import json

from flask import Blueprint, Response, jsonify, request

from miningcat.application import study_language
from miningcat.application.converter import options
from miningcat.application.converter.audiobook_request import AudiobookRequestBuilder
from miningcat.application.converter.jobs import AudiobookJob, VideoJob
from miningcat.application.converter.modes import ConversionMode
from miningcat.application.converter.video_request import VideoRequestBuilder
from miningcat.domain.languages import Language
from miningcat.interfaces.web import uploads
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import JobBusyError, current_state
from miningcat.interfaces.web.requests import converter_language, json_body

bp = Blueprint("converter", __name__)


def refs(value, base=None) -> list:
    """Files sent by the page (their paths under the project's root)."""
    try:
        return uploads.resolve_refs(value or [], base)
    except uploads.InvalidPathError as exc:
        raise UserError("File not available", str(exc))


def start(job, on_done=lambda result: None):
    try:
        current_state().start_job(job, on_done)
    except JobBusyError as exc:
        raise UserError("Busy", str(exc), 409)
    return jsonify(started=True)


@bp.get("/api/options")
def api_options():
    study = study_language.current()
    languages = study_language.converter_languages(study) if study else list(Language)
    return jsonify(options.all_options(languages))


@bp.get("/api/state")
def api_state():
    return jsonify(job=current_state().snapshot(), files=uploads.preload())


@bp.get("/api/events")
def api_events():
    """The log and the progress of the jobs, as Server-Sent Events."""
    state = current_state()
    try:
        last_id = int(request.headers.get("Last-Event-ID") or request.args.get("last") or 0)
    except ValueError:
        last_id = 0

    def stream():
        yield "retry: 2000\n\n"
        for item in state.bus.follow(last_id):
            if item is None:
                yield ": keep-alive\n\n"
                continue
            event_id, event = item
            yield f"id: {event_id}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.post("/api/run/audiobook")
def api_run_audiobook():
    body = json_body()
    try:
        mode = ConversionMode(body.get("mode"))
    except ValueError:
        raise UserError("Unknown mode", f"Unknown mode: {body.get('mode')!r}")
    lang = converter_language(body.get("language"))
    request_ = (
        AudiobookRequestBuilder(mode, lang)
        .audio(refs(body.get("audio")) if mode.needs_audio else [])
        .ebook(refs(body.get("ebook")) if mode.needs_ebook else [], body.get("chapters"))
        .voice(body.get("voice"))
        .whisper(options.model_for(body.get("precision"), lang))
        .convert_to(options.convert_target(body.get("convert"), lang))
        .build()
    )
    state = current_state()
    return start(AudiobookJob(request_), lambda _: state.bus.publish({"type": "done", "kind": "audiobook"}))


@bp.post("/api/run/video")
def api_run_video():
    body = json_body()
    lang = converter_language(body.get("language"))
    builder = VideoRequestBuilder(lang)
    if body.get("input_mode") == "Local file":
        if not body.get("path"):
            raise UserError("Missing file", "Select a local video file.")
        audio_track = body["audio_track"] if isinstance(body.get("audio_track"), int) else None
        builder.local_file(refs([body["path"]])[0], audio_track)
    else:
        url = str(body.get("url") or "").strip()
        if not url:
            raise UserError("Missing URL", "Enter a video URL.")
        url_error = options.validate_video_url(url, body.get("website"))
        if url_error:
            raise UserError("URL mismatch", url_error)
        builder.url(url)
    builder.whisper(options.model_for(body.get("precision"), lang)).convert_to(options.convert_target(body.get("convert"), lang))
    if body.get("ocr"):
        builder.ocr(body.get("ocr_region"), body.get("ocr_fps"))
    state = current_state()

    def on_done(srt_path) -> None:
        state.last_video_srt = srt_path
        state.bus.publish({"type": "done", "kind": "video", "has_srt": srt_path is not None})

    return start(VideoJob(builder.build()), on_done)
