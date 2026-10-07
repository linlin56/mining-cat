import io
import threading

from flask import Blueprint, current_app, jsonify, request, send_file

from game_ocr import capture
from game_ocr.hotkey import DEFAULT_HOTKEY, HOTKEYS
from game_ocr.settings import FULL_REGION, GameOcrSettings
from gui_components.constants import PYTHON
from web.state import AppState, JobBusyError

bp = Blueprint("game", __name__, url_prefix="/api/game")

AREAS = ("screenshot", "text")


class GameError(Exception):
    def __init__(self, message: str, status: int = 400, title: str = "Screen capture"):
        super().__init__(message)
        self.message, self.status, self.title = message, status, title


@bp.errorhandler(GameError)
def _game_error(exc: GameError):
    return jsonify(title=exc.title, error=exc.message), exc.status


@bp.errorhandler(capture.CaptureError)
def _capture_error(exc: capture.CaptureError):
    return jsonify(title="Screen capture", error=str(exc)), 400


def _state() -> AppState:
    return current_app.extensions["miningcat"]


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# Settings saved for another OS (file copied over?) can't be restored here: start from scratch, like the Tkinter panel.
def load_settings() -> GameOcrSettings:
    settings = GameOcrSettings.load()
    info = capture.backend_info()
    if settings.backend is not None and info is not None and settings.backend != info.id:
        return GameOcrSettings()
    return settings


def _check_unlocked() -> None:
    if _state().game_proc is not None:
        raise GameError("Stop the capture before changing the selection.", 409)


def _region(value) -> tuple[float, float, float, float]:
    try:
        region = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        raise GameError("The selected area is invalid.")
    if len(region) != 4 or not all(0.0 <= v <= 1.0 for v in region) or region[2] <= 0 or region[3] <= 0:
        raise GameError("The selected area is invalid.")
    return region


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


# Tag of a language for the /game/ page (dictionary popup, fonts): Cantonese and Taigi aren't Mandarin's zh-Hant.
def language_tag(lang) -> str:
    return lang.tag


@bp.get("/state")
def api_state():
    from game_ocr.server import page_url

    info = capture.backend_info()
    return jsonify(
        language_tag=_state().game_language,
        supported=info is not None,
        backend_label=info.label if info else "Not supported on this OS yet",
        hotkeys=list(HOTKEYS),
        page_url=page_url(),
        running=_state().game_proc is not None,
        settings=describe(load_settings()),
    )


# ---------- window ----------

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
            window_id = _body().get("id")
            window = next((w for w in backend.list_windows() if w.id == window_id), None)
            if window is None:
                raise GameError("This window is gone: refresh the list and pick it again.")
            backend.select_window(window)
        settings = load_settings()
        settings.set_window(info.id, backend.state, backend.window_label)
        settings.save()
    return jsonify(settings=describe(settings))


# ---------- areas ----------

# Grabs a fresh frame of the saved window for the area picker: the whole capture for the screenshot area,
# the screenshot area for the text area (which is relative to it).
@bp.post("/frame")
def api_frame():
    from game_ocr.session import crop_region, open_saved_window

    _check_unlocked()
    area = _body().get("area")
    if area not in AREAS:
        raise GameError(f"Unknown area: {area!r}")
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
    previews = current_app.extensions["miningcat-game-frame"]
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
    data = current_app.extensions["miningcat-game-frame"]["data"]
    if data is None:
        return jsonify(error="No frame captured yet"), 404
    return send_file(io.BytesIO(data), mimetype="image/jpeg", max_age=0)


@bp.post("/area")
def api_area():
    _check_unlocked()
    body = _body()
    area = body.get("area")
    if area not in AREAS:
        raise GameError(f"Unknown area: {area!r}")
    region = _region(body.get("region"))
    settings = load_settings()
    if not settings.has_window:
        raise GameError("Select the game window first.")
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
    body = _body()
    settings = load_settings()
    if body.get("hotkey") in HOTKEYS:
        settings.hotkey = body["hotkey"]
    if "continuous" in body:
        settings.continuous = bool(body["continuous"])
    settings.save()
    return jsonify(settings=describe(settings))


# ---------- capture ----------

# Job target: runs `main.py game serve` until it exits (Stop button, or error), streaming its output to the log.
def run_capture(
    *, state: AppState, lang, convert_target, continuous: bool, hotkey: str,
    schedule, log, set_status, on_done, on_finish,
) -> None:
    from gui_components import pipeline

    exited = threading.Event()
    codes: list[int] = []

    def on_exit(returncode: int) -> None:
        codes.append(returncode)
        exited.set()

    try:
        # The /game/ page of MiningCat replaces the capture server's own page (opened by the web GUI).
        state.game_language = language_tag(lang)
        state.game_proc = pipeline.start_game_server(
            python_exe=PYTHON, lang=lang, convert_target=convert_target,
            continuous=continuous, hotkey=hotkey,
            schedule=schedule, log=log, on_exit=on_exit, open_browser=False,
        )
        set_status("Capturing - the page opens in your browser", 100)
        exited.wait()
        log(f"\nCapture stopped (code {codes[0]}).\n")
        set_status("Capture stopped", 0)
        on_done()
    except Exception as exc:
        log(f"\n[ERROR] {exc}\n")
        set_status("Error - check the log.", 0)
    finally:
        state.game_proc = None
        state.game_language = None
        on_finish()


@bp.post("/start")
def api_start():
    from web.app import UserError, _convert_target, _language

    body = _body()
    lang = _language(body.get("language"))
    settings = load_settings()
    if capture.backend_info() is None:
        raise UserError("Not supported", "Video game / screen share capture isn't supported on this OS yet.")
    if not settings.is_ready:
        raise UserError("Missing selection", "Select the game window and its text area first.")
    state = _state()
    try:
        state.start_job(
            "game", run_capture, lambda: None,
            state=state,
            lang=lang,
            convert_target=_convert_target(body.get("convert"), lang),
            continuous=settings.continuous,
            hotkey=settings.hotkey if settings.hotkey in HOTKEYS else DEFAULT_HOTKEY,
        )
    except JobBusyError as exc:
        raise UserError("Busy", str(exc), 409)
    return jsonify(started=True)


@bp.post("/stop")
def api_stop():
    from gui_components import pipeline

    proc = _state().game_proc
    if proc is not None:
        threading.Thread(target=pipeline.stop_game_server, args=(proc,), daemon=True).start()
    return jsonify(stopping=proc is not None)
