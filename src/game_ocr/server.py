import asyncio
import base64
import io
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import WSMsgType, web
from PIL import Image

from game_ocr.capture import CaptureError
from game_ocr.hotkey import Hotkey
from game_ocr.session import CaptureResult, GameOcrSession
from language import Language

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6677
DEFAULT_INTERVAL_S = 0.5

PAGE_FILE = Path(__file__).parent / "page.html"
STYLE_FILE = Path(__file__).parent / "page.css"

_HISTORY_MAX = 200
_HISTORY_REPLAY = 20
# Retina captures are huge: the page only needs a readable screenshot.
_SCREENSHOT_MAX_DIM = 1600
# After a capture error (window closed, permission revoked...), wait longer before retrying, to avoid flooding the log.
_ERROR_BACKOFF_S = 3.0


def page_url(port: int = DEFAULT_PORT) -> str:
    return f"http://{DEFAULT_HOST}:{port}/"


def encode_screenshot(image: Image.Image) -> str:
    image = image.copy()
    image.thumbnail((_SCREENSHOT_MAX_DIM, _SCREENSHOT_MAX_DIM))
    buf = io.BytesIO()
    image.save(buf, format="webp", quality=88)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def build_payload(result: CaptureResult) -> dict:
    return {
        "type": "capture",
        "text": result.text,
        "image": encode_screenshot(result.screenshot),
        "ts": time.strftime("%H:%M:%S"),
        "ms": result.ms,
    }


class Hub:
    def __init__(self):
        self.sockets: set = set()
        self.history: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.history = (self.history + [payload])[-_HISTORY_MAX:]
        await self._send_all(payload)

    async def clear(self) -> None:
        self.history = []
        await self._send_all({"type": "clear"})

    async def _send_all(self, payload: dict) -> None:
        dead = []
        for ws in self.sockets:
            try:
                await ws.send_json(payload)
            except ConnectionResetError:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


SESSION_KEY = web.AppKey("session", GameOcrSession)
LANGUAGE_KEY = web.AppKey("language", Language)
HUB_KEY = web.AppKey("hub", Hub)
EXECUTOR_KEY = web.AppKey("executor", ThreadPoolExecutor)
AUTO_KEY = web.AppKey("auto", bool)
HOTKEY_KEY = web.AppKey("hotkey", object)  # Hotkey | None
PORT_KEY = web.AppKey("port", int)
INTERVAL_KEY = web.AppKey("interval", float)


# Captures in the single-thread executor (backends and OCR engines aren't thread-safe), then pushes the result to every tab.
async def capture_and_broadcast(app: web.Application, force: bool) -> tuple[dict | None, str]:
    session: GameOcrSession = app[SESSION_KEY]
    loop = asyncio.get_running_loop()
    result, reason = await loop.run_in_executor(app[EXECUTOR_KEY], session.capture, force)
    if result is None:
        return None, reason
    payload = build_payload(result)
    await app[HUB_KEY].broadcast(payload)
    print(f"[capture] {payload['ms']} ms - {result.text[:60]}", flush=True)
    return payload, ""


async def _auto_capture_loop(app: web.Application) -> None:
    interval = app[INTERVAL_KEY]
    last_error = None
    while True:
        delay = interval
        try:
            await capture_and_broadcast(app, force=False)
            last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if str(exc) != last_error:
                print(f"[auto capture] failed: {exc}", flush=True)
                last_error = str(exc)
            delay = max(interval, _ERROR_BACKOFF_S)
        await asyncio.sleep(delay)


async def _auto_capture_ctx(app: web.Application):
    task = asyncio.create_task(_auto_capture_loop(app))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# Starts listening to the capture key, and stops with the server.
# A key that can't be set up (missing permission...) is explained in the log, but doesn't stop the capture:
# the page's button still works.
async def _hotkey_ctx(app: web.Application):
    hotkey: Hotkey = app[HOTKEY_KEY]
    loop = asyncio.get_running_loop()

    def report(future) -> None:
        exc = future.exception()
        if exc is not None:
            print(f"[capture] failed: {exc}", flush=True)
        else:
            payload, reason = future.result()
            if payload is None:
                print(f"[capture] skipped: {reason}", flush=True)

    # Called from the hotkey's own thread.
    def on_press() -> None:
        asyncio.run_coroutine_threadsafe(capture_and_broadcast(app, force=True), loop).add_done_callback(report)

    started = False
    try:
        hotkey.start(on_press, page_url(app[PORT_KEY]) + "capture")
        started = True
        print(f"Key:       press {hotkey.key} to capture", flush=True)
    except Exception as exc:
        print(f"[capture key] {hotkey.key} unavailable: {exc}", flush=True)
    yield
    if started:
        hotkey.stop()


async def handle_capture(request: web.Request) -> web.Response:
    try:
        payload, reason = await capture_and_broadcast(request.app, force=True)
    except CaptureError as exc:
        print(f"[capture] failed: {exc}", flush=True)
        return web.json_response({"error": str(exc)}, status=500)
    if payload is None:
        return web.json_response({"skipped": reason})
    return web.json_response({"ok": True, "ms": payload["ms"]})


async def handle_clear(request: web.Request) -> web.Response:
    request.app[SESSION_KEY].forget_last_text()
    await request.app[HUB_KEY].clear()
    return web.json_response({"ok": True})


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    hub: Hub = request.app[HUB_KEY]
    ws = web.WebSocketResponse(max_msg_size=32 * 1024 * 1024)
    await ws.prepare(request)
    hub.sockets.add(ws)
    for item in hub.history[-_HISTORY_REPLAY:]:
        await ws.send_json(item)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        hub.sockets.discard(ws)
    return ws


async def handle_index(request: web.Request) -> web.Response:
    language: Language = request.app[LANGUAGE_KEY]
    html = PAGE_FILE.read_text(encoding="utf-8")
    html = (html
            .replace("{{LANG}}", language.value.ocr_lang_apple)
            .replace("{{AUTO}}", "true" if request.app[AUTO_KEY] else "false")
            .replace("{{HOTKEY}}", request.app[HOTKEY_KEY].key if request.app[HOTKEY_KEY] else ""))
    return web.Response(text=html, content_type="text/html")


async def handle_style(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(STYLE_FILE)


def create_app(
    session: GameOcrSession,
    language: Language,
    auto: bool = False,
    interval: float = DEFAULT_INTERVAL_S,
    hotkey: Hotkey | None = None,
    port: int = DEFAULT_PORT,
) -> web.Application:
    app = web.Application()
    app[SESSION_KEY] = session
    app[LANGUAGE_KEY] = language
    app[HUB_KEY] = Hub()
    app[EXECUTOR_KEY] = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game-ocr")
    app[AUTO_KEY] = auto
    app[INTERVAL_KEY] = interval
    app[HOTKEY_KEY] = hotkey
    app[PORT_KEY] = port
    app.router.add_get("/", handle_index)
    app.router.add_get("/page.css", handle_style)
    app.router.add_get("/ws", handle_ws)
    app.router.add_post("/capture", handle_capture)
    app.router.add_post("/clear", handle_clear)
    if auto:
        app.cleanup_ctx.append(_auto_capture_ctx)
    if hotkey is not None:
        app.cleanup_ctx.append(_hotkey_ctx)

    async def shutdown_executor(app):
        app[EXECUTOR_KEY].shutdown(wait=False, cancel_futures=True)

    app.on_cleanup.append(shutdown_executor)
    return app


# Blocks until the server is stopped (Ctrl+C, or SIGTERM from the GUI's Stop button).
def run(app: web.Application, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    if open_browser:
        # on_startup runs just before the socket starts listening: give it a moment.
        async def open_page(_app):
            asyncio.get_running_loop().call_later(0.5, webbrowser.open, page_url(port))
        app.on_startup.append(open_page)
    web.run_app(app, host=DEFAULT_HOST, port=port, print=None)
