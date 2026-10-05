import asyncio
import base64
import io
from unittest.mock import MagicMock, patch

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from game_ocr import server
from game_ocr.capture import CaptureError
from game_ocr.session import CaptureResult
from language import Language


# Stands in for GameOcrSession: returns queued capture outcomes.
class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.forced = []
        self.forgot = 0

    def capture(self, force=False):
        self.forced.append(force)
        outcome = self.outcomes.pop(0) if self.outcomes else (None, "text area unchanged")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def forget_last_text(self):
        self.forgot += 1


def _result(text="你好"):
    return CaptureResult(text=text, screenshot=Image.new("RGB", (40, 20), "red"), ms=12), ""


def _run(session, check, auto=False, interval=0.01, language=Language.MANDARIN_TW, hotkey=None):
    async def main():
        app = server.create_app(session, language, auto=auto, interval=interval, hotkey=hotkey, port=7010)
        async with TestClient(TestServer(app)) as client:
            await check(client, app)
    asyncio.run(main())


def test_page_url():
    assert server.page_url(7000) == "http://127.0.0.1:7000/"


def test_encode_screenshot_downscales_to_webp_data_url():
    url = server.encode_screenshot(Image.new("RGB", (3200, 1800)))
    assert url.startswith("data:image/webp;base64,")
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert max(image.size) == 1600


def test_build_payload():
    result, _ = _result("早安")
    payload = server.build_payload(result)
    assert payload["type"] == "capture"
    assert payload["text"] == "早安"
    assert payload["ms"] == 12
    assert payload["image"].startswith("data:image/webp")


def test_index_injects_language_and_auto_mode():
    async def check(client, _app):
        html = await (await client.get("/")).text()
        assert '<html lang="ja-JP">' in html
        assert "const AUTO    = false;" in html
        assert "{{" not in html
    _run(FakeSession(), check, language=Language.JAPANESE)


def test_page_links_its_stylesheet_which_is_served():
    async def check(client, _app):
        html = await (await client.get("/")).text()
        assert '<link rel="stylesheet" href="/page.css">' in html
        response = await client.get("/page.css")
        assert response.status == 200
        assert response.content_type == "text/css"
        assert "--ground" in await response.text()
    _run(FakeSession(), check)


def test_manual_capture_broadcasts_to_websocket_and_keeps_history():
    session = FakeSession(_result("你好"))

    async def check(client, app):
        ws = await client.ws_connect("/ws")
        response = await client.post("/capture")
        assert await response.json() == {"ok": True, "ms": 12}
        message = await ws.receive_json()
        assert message["text"] == "你好"
        assert app[server.HUB_KEY].history == [message]
        await ws.close()
    _run(session, check)
    assert session.forced == [True]


def test_manual_capture_reports_skipped_reason():
    async def check(client, _app):
        response = await client.post("/capture")
        assert await response.json() == {"skipped": "no text detected"}
    _run(FakeSession((None, "no text detected")), check)


def test_manual_capture_error_returns_500():
    async def check(client, _app):
        response = await client.post("/capture")
        assert response.status == 500
        assert await response.json() == {"error": "window gone"}
    _run(FakeSession(CaptureError("window gone")), check)


def test_websocket_replays_recent_history():
    async def check(client, app):
        app[server.HUB_KEY].history = [{"type": "capture", "text": str(i)} for i in range(30)]
        ws = await client.ws_connect("/ws")
        replayed = [await ws.receive_json() for _ in range(20)]
        assert [m["text"] for m in replayed] == [str(i) for i in range(10, 30)]
        await ws.close()
    _run(FakeSession(), check)


def test_clear_empties_history_notifies_tabs_and_forgets_last_text():
    session = FakeSession()

    async def check(client, app):
        app[server.HUB_KEY].history = [{"type": "capture", "text": "x"}]
        ws = await client.ws_connect("/ws")
        await ws.receive_json()  # replayed history
        assert await (await client.post("/clear")).json() == {"ok": True}
        assert await ws.receive_json() == {"type": "clear"}
        assert app[server.HUB_KEY].history == []
        await ws.close()
    _run(session, check)
    assert session.forgot == 1


def test_hub_history_is_bounded():
    hub = server.Hub()

    async def main():
        for i in range(server._HISTORY_MAX + 5):
            await hub.broadcast({"i": i})
    asyncio.run(main())
    assert len(hub.history) == server._HISTORY_MAX
    assert hub.history[0] == {"i": 5}


def test_hub_drops_disconnected_sockets():
    hub = server.Hub()
    dead = MagicMock()
    dead.send_json.side_effect = ConnectionResetError
    hub.sockets.add(dead)
    asyncio.run(hub.clear())
    assert hub.sockets == set()


def test_auto_capture_loop_pushes_changes_and_survives_errors(capsys):
    session = FakeSession((None, "text area unchanged"), CaptureError("window gone"), _result("自動"))

    async def check(client, _app):
        ws = await client.ws_connect("/ws")
        message = await asyncio.wait_for(ws.receive_json(), 5)
        assert message["text"] == "自動"
        await ws.close()

    with patch.object(server, "_ERROR_BACKOFF_S", 0.01):
        _run(session, check, auto=True)
    assert session.forced[:3] == [False, False, False]
    assert "[auto capture] failed: window gone" in capsys.readouterr().out


def test_run_opens_browser_on_startup():
    app = MagicMock()
    app.on_startup = []
    with patch.object(server.web, "run_app") as run_app:
        server.run(app, port=7001, open_browser=True)
    run_app.assert_called_once_with(app, host="127.0.0.1", port=7001, print=None)
    assert len(app.on_startup) == 1

    async def startup():
        with patch.object(server.webbrowser, "open") as open_browser:
            await app.on_startup[0](app)
            await asyncio.sleep(0.6)
        open_browser.assert_called_once_with("http://127.0.0.1:7001/")
    asyncio.run(startup())


def test_run_without_browser():
    app = MagicMock()
    app.on_startup = []
    with patch.object(server.web, "run_app"):
        server.run(app, open_browser=False)
    assert app.on_startup == []


# capture key
class FakeHotkey:
    key = "F9"

    def __init__(self, fail=None):
        self.fail = fail
        self.on_press = None
        self.url = None
        self.stopped = False

    def start(self, on_press, capture_url):
        if self.fail:
            raise self.fail
        self.on_press, self.url = on_press, capture_url

    def stop(self):
        self.stopped = True


def test_page_mentions_the_capture_key():
    async def check(client, _app):
        html = await (await client.get("/")).text()
        assert 'const HOTKEY  = "F9";' in html
    _run(FakeSession(), check, hotkey=FakeHotkey())


def test_capture_key_press_captures_and_broadcasts(capsys):
    hotkey = FakeHotkey()
    session = FakeSession(_result("按鍵"), (None, "same text as the previous capture"))

    async def check(client, _app):
        assert hotkey.url == "http://127.0.0.1:7010/capture"
        ws = await client.ws_connect("/ws")
        # the key listener calls on_press from its own thread
        await asyncio.to_thread(hotkey.on_press)
        message = await asyncio.wait_for(ws.receive_json(), 5)
        assert message["text"] == "按鍵"
        await asyncio.to_thread(hotkey.on_press)
        await asyncio.sleep(0.1)
        await ws.close()

    _run(session, check, hotkey=hotkey)
    assert session.forced == [True, True]
    assert hotkey.stopped
    out = capsys.readouterr().out
    assert "press F9 to capture" in out
    assert "skipped: same text" in out


def test_capture_key_error_is_logged(capsys):
    hotkey = FakeHotkey()

    async def check(_client, _app):
        await asyncio.to_thread(hotkey.on_press)
        await asyncio.sleep(0.1)

    _run(FakeSession(CaptureError("window gone")), check, hotkey=hotkey)
    assert "[capture] failed: window gone" in capsys.readouterr().out


def test_unavailable_capture_key_keeps_serving(capsys):
    hotkey = FakeHotkey(fail=RuntimeError("needs Input Monitoring"))

    async def check(client, _app):
        assert (await client.get("/")).status == 200

    _run(FakeSession(), check, hotkey=hotkey)
    assert "F9 unavailable: needs Input Monitoring" in capsys.readouterr().out
    assert not hotkey.stopped
