"""The Video game / Screen share source of the converter: the window and areas saved in sources/game_ocr.json (window
list, a fresh capture for the area picker), and the capture run as a job."""
import io
import threading

from flask import Blueprint, jsonify, send_file

from miningcat.application.converter import options
from miningcat.application.converter.jobs import Job
from miningcat.application.converter.progress import ProgressListener
from miningcat.application.game_ocr.capture_process import GameCaptureProcess
from miningcat.application.game_ocr.session import crop_region, open_saved_window
from miningcat.application.game_ocr.settings import GameOcrSettings
from miningcat.domain.languages import Language
from miningcat.domain.ocr.regions import FULL_REGION, Region, valid_region
from miningcat.infrastructure import capture
from miningcat.infrastructure.hotkeys import DEFAULT_HOTKEY, HOTKEYS
from miningcat.interfaces.game_page.address import page_url
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import AppState, JobBusyError, current_state
from miningcat.interfaces.web.requests import converter_language, json_body

bp = Blueprint("game", __name__, url_prefix="/api/game")

AREAS = ("screenshot", "text")


def _error(message: str, status: int = 400) -> UserError:
    return UserError("Screen capture", message, status)


# Settings saved for another OS (file copied over?) can't be restored here: start from scratch.
def load_settings() -> GameOcrSettings:
    settings = GameOcrSettings.load()
    info = capture.backend_info()
    if settings.backend is not None and info is not None and settings.backend != info.id:
        return GameOcrSettings()
    return settings


def _check_unlocked() -> None:
    if current_state().game_capture is not None:
        raise _error("Stop the capture before changing the selection.", 409)


def _region(value) -> Region:
    try:
        return valid_region(value)
    except (TypeError, ValueError):
        raise _error("The selected area is invalid.")


def describe(settings: GameOcrSettings) -> dict:
    return {
        "window_label": settings.window_label,
        "has_window": settings.has_window,
        "screenshot_region": list(settings.screenshot_region) if settings.screenshot_region else None,
        "text_region": list(settings.text_region) if settings.text_region else None,
        "hotkey": settings.hotkey if settings.hotkey in HOTKEYS else DEFAULT_HOTKEY,
        "continuous": settings.continuous,
        "is_ready": settings.is_ready,
    }


@bp.get("/state")
def api_state():
    info = capture.backend_info()
    return jsonify(
        language_tag=current_state().game_language,
        supported=info is not None,
        backend_label=info.label if info else "Not supported on this OS yet",
        hotkeys=list(HOTKEYS),
        page_url=page_url(),
        running=current_state().game_capture is not None,
        settings=describe(load_settings()),
    )


# Backends with a system picker (Wayland portal) don't list windows: the OS asks the user on select.
@bp.get("/windows")
def api_windows():
    backend = capture.create_backend()
    try:
        if backend.has_system_picker:
            return jsonify(system_picker=True, windows=[])
        windows = backend.list_windows()
    finally:
        backend.close()
    return jsonify(system_picker=False, windows=[{"id": w.id, "label": w.label} for w in windows])


# Body: {"id": window id from /windows}, ignored with a system picker (its dialog blocks until the user answers).
@bp.post("/window")
def api_select_window():
    _check_unlocked()
    info = capture.backend_info()
    backend = capture.create_backend()
    with backend:
        if backend.has_system_picker:
            backend.select_window()
        else:
            window_id = json_body().get("id")
            window = next((w for w in backend.list_windows() if w.id == window_id), None)
            if window is None:
                raise _error("This window is gone: refresh the list and pick it again.")
            backend.select_window(window)
        settings = load_settings()
        settings.set_window(info.id, backend.state, backend.window_label)
        settings.save()
    return jsonify(settings=describe(settings))


# Grabs a fresh frame of the saved window for the area picker: the whole capture for the screenshot area,
# the screenshot area for the text area (which is relative to it).
@bp.post("/frame")
def api_frame():
    _check_unlocked()
    area = json_body().get("area")
    if area not in AREAS:
        raise _error(f"Unknown area: {area!r}")
    settings = load_settings()
    with open_saved_window(settings) as backend:
        frame = backend.grab_frame()
    if area == "text":
        frame = crop_region(frame, settings.screenshot_region)
        region = settings.text_region
    else:
        region = settings.screenshot_region
    buf = io.BytesIO()
    frame.save(buf, format="JPEG", quality=90)
    previews = current_state().game_frame
    previews["data"] = buf.getvalue()
    previews["version"] += 1
    return jsonify(
        frame=f"/api/game/frame.jpg?v={previews['version']}",
        width=frame.width, height=frame.height,
        region=list(region or FULL_REGION),
        settings=describe(settings),
    )


@bp.get("/frame.jpg")
def api_frame_image():
    data = current_state().game_frame["data"]
    if data is None:
        return jsonify(error="No frame captured yet"), 404
    return send_file(io.BytesIO(data), mimetype="image/jpeg", max_age=0)


@bp.post("/area")
def api_area():
    _check_unlocked()
    body = json_body()
    area = body.get("area")
    if area not in AREAS:
        raise _error(f"Unknown area: {area!r}")
    region = _region(body.get("region"))
    settings = load_settings()
    if not settings.has_window:
        raise _error("Select the game window first.")
    if area == "screenshot":
        settings.set_screenshot_region(region)
    else:
        settings.text_region = region
    settings.save()
    return jsonify(settings=describe(settings))


# How captures are triggered: the capture key, or continuously when the text changes. Remembered for next time.
@bp.post("/trigger")
def api_trigger():
    _check_unlocked()
    body = json_body()
    settings = load_settings()
    if body.get("hotkey") in HOTKEYS:
        settings.hotkey = body["hotkey"]
    if "continuous" in body:
        settings.continuous = bool(body["continuous"])
    settings.save()
    return jsonify(settings=describe(settings))


class GameCaptureJob(Job):
    """Runs `python -m miningcat game serve` until it exits (Stop button, or error), its output in the job's log."""

    kind = "game"

    def __init__(self, state: AppState, language: Language, process: GameCaptureProcess):
        self.state, self.language, self.process = state, language, process

    def run(self, listener: ProgressListener) -> None:
        exited = threading.Event()
        codes: list[int] = []

        def on_exit(returncode: int) -> None:
            codes.append(returncode)
            exited.set()

        try:
            # The /game/ page of MiningCat replaces the capture server's own page (opened by the web GUI).
            self.state.game_language = self.language.profile.tag
            self.state.game_capture = self.process
            self.process.start(listener.log, on_exit)
            listener.status("Capturing - the page opens in your browser", 100)
            exited.wait()
            listener.log(f"\nCapture stopped (code {codes[0]}).\n")
            listener.status("Capture stopped", 0)
        finally:
            self.state.game_capture = None
            self.state.game_language = None


@bp.post("/start")
def api_start():
    body = json_body()
    lang = converter_language(body.get("language"))
    settings = load_settings()
    if capture.backend_info() is None:
        raise UserError("Not supported", "Video game / screen share capture isn't supported on this OS yet.")
    if not settings.is_ready:
        raise UserError("Missing selection", "Select the game window and its text area first.")
    state = current_state()
    process = GameCaptureProcess(
        lang, options.convert_target(body.get("convert"), lang), continuous=settings.continuous,
        hotkey=settings.hotkey if settings.hotkey in HOTKEYS else DEFAULT_HOTKEY, open_browser=False,
    )
    try:
        state.start_job(GameCaptureJob(state, lang, process))
    except JobBusyError as exc:
        raise UserError("Busy", str(exc), 409)
    return jsonify(started=True)


@bp.post("/stop")
def api_stop():
    process = current_state().game_capture
    if process is not None:
        threading.Thread(target=process.stop, daemon=True).start()
    return jsonify(stopping=process is not None)
