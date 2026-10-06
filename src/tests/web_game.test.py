import pytest

pytest.importorskip("flask")

from PIL import Image

from game_ocr import capture
from game_ocr.capture import BackendInfo, CaptureBackend, CaptureError, WindowInfo
from game_ocr.settings import GameOcrSettings
from language import Language
from web import app as web_app
from web import game
from web.state import AppState

HEADERS = {"X-MiningCat": "1"}
INFO = BackendInfo(id="fake", label="Fake OS", platforms=("fake",), module="", class_name="")


class FakeBackend(CaptureBackend):
    has_system_picker = False
    windows = [WindowInfo(1, "Ryujinx", "Zelda"), WindowInfo(2, "Safari")]

    def __init__(self):
        self._window = None
        self.closed = False

    def list_windows(self):
        return self.windows

    def select_window(self, window=None):
        self._window = window or WindowInfo(9, "Portal pick")

    def restore(self, state):
        self._window = WindowInfo(state["id"], state["owner"])

    @property
    def state(self):
        return {"id": self._window.id, "owner": self._window.owner}

    @property
    def window_label(self):
        return self._window.label

    def grab_frame(self):
        return Image.new("RGB", (200, 100), "white")

    def close(self):
        self.closed = True


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr(capture, "backend_info", lambda platform=None: INFO)
    monkeypatch.setattr(capture, "create_backend", lambda platform=None: FakeBackend())
    return FakeBackend


@pytest.fixture
def state():
    return AppState()


@pytest.fixture
def client(state):
    app = web_app.create_app(state)
    app.testing = True
    return app.test_client()


def post(client, url, json=None):
    return client.post(url, json=json if json is not None else {}, headers=HEADERS)


def ready_settings() -> GameOcrSettings:
    settings = GameOcrSettings(
        backend="fake", backend_state={"id": 1, "owner": "Ryujinx"}, window_label="Ryujinx - Zelda",
        text_region=(0, 0.5, 1, 0.5),
    )
    settings.save()
    return settings


def test_game_is_a_source(client):
    assert "Video game / Screen share" in client.get("/api/options").get_json()["sources"]


def test_state_describes_the_saved_selection(client, backend):
    ready_settings()
    data = client.get("/api/game/state").get_json()
    assert data["supported"] is True
    assert data["backend_label"] == "Fake OS"
    assert data["hotkeys"][0] == "F1"
    assert data["running"] is False
    assert data["settings"]["window_label"] == "Ryujinx - Zelda"
    assert data["settings"]["is_ready"] is True
    assert data["settings"]["hotkey"] == "F9"


def test_unsupported_os(client, monkeypatch):
    monkeypatch.setattr(capture, "backend_info", lambda platform=None: None)
    data = client.get("/api/game/state").get_json()
    assert data["supported"] is False
    response = post(client, "/api/game/start", {"language": "japanese"})
    assert response.status_code == 400


def test_settings_of_another_os_are_ignored(client, backend):
    GameOcrSettings(backend="linux_wayland", backend_state={"token": "x"}, window_label="Other").save()
    assert client.get("/api/game/state").get_json()["settings"]["has_window"] is False


def test_list_then_select_a_window(client, backend):
    data = client.get("/api/game/windows").get_json()
    assert data == {"system_picker": False, "windows": [{"id": 1, "label": "Ryujinx - Zelda"}, {"id": 2, "label": "Safari"}]}
    data = post(client, "/api/game/window", {"id": 2}).get_json()
    assert data["settings"]["window_label"] == "Safari"
    assert GameOcrSettings.load().backend_state == {"id": 2, "owner": "Safari"}


def test_selecting_a_gone_window_fails(client, backend):
    response = post(client, "/api/game/window", {"id": 42})
    assert response.status_code == 400
    assert "gone" in response.get_json()["error"]


def test_system_picker_selects_without_a_list(client, backend, monkeypatch):
    monkeypatch.setattr(FakeBackend, "has_system_picker", True)
    assert client.get("/api/game/windows").get_json() == {"system_picker": True, "windows": []}
    data = post(client, "/api/game/window").get_json()
    assert data["settings"]["window_label"] == "Portal pick"


def test_capture_errors_are_shown(client, monkeypatch):
    monkeypatch.setattr(capture, "backend_info", lambda platform=None: INFO)

    def denied(platform=None):
        raise CaptureError("MiningCat needs the Screen Recording permission")

    monkeypatch.setattr(capture, "create_backend", denied)
    response = client.get("/api/game/windows")
    assert response.status_code == 400
    assert "Screen Recording" in response.get_json()["error"]


def test_frame_for_the_text_area_is_cropped_to_the_screenshot_area(client, backend):
    settings = ready_settings()
    settings.set_screenshot_region((0, 0, 0.5, 1))
    settings.save()
    data = post(client, "/api/game/frame", {"area": "text"}).get_json()
    assert (data["width"], data["height"]) == (100, 100)
    # The text area was reset with the screenshot area: the picker starts on the whole image.
    assert data["region"] == [0, 0, 1, 1]
    image = client.get(data["frame"])
    assert image.mimetype == "image/jpeg"


def test_frame_needs_a_window(client, backend):
    response = post(client, "/api/game/frame", {"area": "screenshot"})
    assert response.status_code == 400


def test_frame_image_before_any_capture(client):
    assert client.get("/api/game/frame.jpg").status_code == 404


def test_new_screenshot_area_resets_the_text_area(client, backend):
    ready_settings()
    data = post(client, "/api/game/area", {"area": "screenshot", "region": [0.1, 0.1, 0.8, 0.8]}).get_json()
    assert data["settings"]["screenshot_region"] == [0.1, 0.1, 0.8, 0.8]
    assert data["settings"]["text_region"] is None
    data = post(client, "/api/game/area", {"area": "text", "region": [0, 0.6, 1, 0.4]}).get_json()
    assert data["settings"]["is_ready"] is True


@pytest.mark.parametrize("body", [
    {"area": "nope", "region": [0, 0, 1, 1]},
    {"area": "text", "region": [0, 0, 2, 1]},
    {"area": "text", "region": "all"},
    {"area": "text", "region": [0, 0, 0, 1]},
])
def test_invalid_areas_are_refused(client, backend, body):
    ready_settings()
    assert post(client, "/api/game/area", body).status_code == 400


def test_area_needs_a_window(client, backend):
    assert post(client, "/api/game/area", {"area": "text", "region": [0, 0, 1, 1]}).status_code == 400


def test_trigger_is_remembered(client, backend):
    post(client, "/api/game/trigger", {"hotkey": "F2", "continuous": True})
    settings = GameOcrSettings.load()
    assert (settings.hotkey, settings.continuous) == ("F2", True)
    post(client, "/api/game/trigger", {"hotkey": "Escape"})
    assert GameOcrSettings.load().hotkey == "F2"


def test_start_needs_a_ready_selection(client, backend):
    response = post(client, "/api/game/start", {"language": "japanese"})
    assert response.status_code == 400
    assert response.get_json()["title"] == "Missing selection"


class FakeProc:
    def __init__(self):
        self.on_exit = None


def test_start_runs_the_capture_until_it_exits(client, state, backend, monkeypatch):
    import web.state
    from gui_components import pipeline

    ready_settings()
    post(client, "/api/game/trigger", {"continuous": True})
    started = {}
    threads = []

    def fake_start(**kwargs):
        started.update(kwargs)
        kwargs["log"]("Page: http://127.0.0.1:6677/\n")
        return FakeProc()

    class KeptThread:
        def __init__(self, target, daemon=None, name=None):
            threads.append(target)

        def start(self):
            pass

    monkeypatch.setattr(pipeline, "start_game_server", fake_start)
    monkeypatch.setattr(web.state.threading, "Thread", KeptThread)
    assert post(client, "/api/game/start", {"language": "mandarin_tw", "convert": "Simplified - China"}).status_code == 200
    assert state.running

    # The job thread blocks until the subprocess exits: run it, with the subprocess exiting right away.
    real_event = game.threading.Event

    class ExitedEvent:
        def __init__(self):
            self._event = real_event()

        def set(self):
            self._event.set()

        def wait(self):
            started["on_exit"](0)

    monkeypatch.setattr(game.threading, "Event", ExitedEvent)
    threads[0]()

    assert started["lang"] is Language.MANDARIN_TW
    assert started["convert_target"] == "s"
    assert started["continuous"] is True
    assert started["open_browser"] is False
    assert not state.running
    assert state.game_language is None
    assert state.game_proc is None
    texts = [e.get("text", "") for _, e in state.bus.events_after(0)]
    assert "Page: http://127.0.0.1:6677/\n" in texts
    assert "\nCapture stopped (code 0).\n" in texts
    assert {"type": "finish", "kind": "game"} in [e for _, e in state.bus.events_after(0)]


def test_start_failure_ends_the_job(state, monkeypatch):
    from gui_components import pipeline

    def boom(**kwargs):
        raise OSError("python not found")

    monkeypatch.setattr(pipeline, "start_game_server", boom)
    finished = []
    logs = []
    game.run_capture(
        state=state, lang=Language.JAPANESE, convert_target=None, continuous=False, hotkey="F9",
        schedule=None, log=logs.append, set_status=lambda *a: None,
        on_done=lambda: None, on_finish=lambda: finished.append(True),
    )
    assert finished == [True]
    assert "python not found" in "".join(logs)


def test_selection_is_locked_while_capturing(client, state, backend):
    ready_settings()
    state.game_proc = FakeProc()
    assert post(client, "/api/game/area", {"area": "text", "region": [0, 0, 1, 1]}).status_code == 409
    assert post(client, "/api/game/window", {"id": 1}).status_code == 409
    assert client.get("/api/game/state").get_json()["running"] is True


def test_stop_terminates_the_subprocess(client, state, monkeypatch):
    from gui_components import pipeline

    stopped = []
    monkeypatch.setattr(pipeline, "stop_game_server", lambda proc: stopped.append(proc))
    monkeypatch.setattr(game.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    assert post(client, "/api/game/stop").get_json() == {"stopping": False}
    proc = FakeProc()
    state.game_proc = proc
    assert post(client, "/api/game/stop").get_json() == {"stopping": True}
    assert stopped == [proc]


def test_language_tag_of_the_running_game(client, state, backend):
    state.game_proc, state.game_language = FakeProc(), "zh-Hant"
    assert client.get("/api/game/state").get_json()["language_tag"] == "zh-Hant"
    assert game.language_tag(Language.CANTONESE_HK) == "yue-Hant"
    assert game.language_tag(Language.JAPANESE) == "ja-JP"


def test_game_page(client):
    page = client.get("/game/")
    assert page.status_code == 200 and b"game.js" in page.data
