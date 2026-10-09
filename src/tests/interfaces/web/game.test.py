import pytest

pytest.importorskip("flask")

from PIL import Image

from miningcat.application.game_ocr.settings import GameOcrSettings
from miningcat.domain.languages import Language
from miningcat.infrastructure import capture
from miningcat.infrastructure.capture import BackendInfo, CaptureBackend, CaptureError, WindowInfo
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web import jobs as web_jobs
from miningcat.interfaces.web.blueprints import game
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}
INFO = BackendInfo(id="fake", label="Fake OS", platforms=("fake",), module="", class_name="")


class FakeBackend(CaptureBackend):
    has_system_picker = False
    windows = [WindowInfo(1, "SampleApp", "Sample Quest"), WindowInfo(2, "Browser")]

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
        backend="fake", backend_state={"id": 1, "owner": "SampleApp"}, window_label="SampleApp - Sample Quest",
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
    assert data["settings"]["window_label"] == "SampleApp - Sample Quest"
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
    assert data == {"system_picker": False, "windows": [{"id": 1, "label": "SampleApp - Sample Quest"}, {"id": 2, "label": "Browser"}]}
    data = post(client, "/api/game/window", {"id": 2}).get_json()
    assert data["settings"]["window_label"] == "Browser"
    assert GameOcrSettings.load().backend_state == {"id": 2, "owner": "Browser"}


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


class FakeCapture:
    """Stands for GameCaptureProcess: its process prints a line and exits right away."""

    created = []

    def __init__(self, language, convert_target, continuous, hotkey, open_browser=True):
        self.args = dict(language=language, convert_target=convert_target, continuous=continuous, hotkey=hotkey,
                         open_browser=open_browser)
        self.stopped = False
        FakeCapture.created.append(self)

    def start(self, on_line, on_exit):
        on_line("Page: http://127.0.0.1:6677/\n")
        on_exit(0)

    def stop(self):
        self.stopped = True


class SyncThread:
    def __init__(self, target, args=(), daemon=None, name=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def test_start_runs_the_capture_until_it_exits(client, state, backend, monkeypatch):
    ready_settings()
    post(client, "/api/game/trigger", {"continuous": True})
    FakeCapture.created = []
    monkeypatch.setattr(game, "GameCaptureProcess", FakeCapture)
    monkeypatch.setattr(web_jobs.threading, "Thread", SyncThread)
    assert post(client, "/api/game/start", {"language": "mandarin_tw", "convert": "Simplified - China"}).status_code == 200

    args = FakeCapture.created[0].args
    assert args["language"] is Language.MANDARIN_TW
    assert args["convert_target"] == "s"
    assert args["continuous"] is True
    assert args["open_browser"] is False
    assert not state.running
    assert state.game_language is None
    assert state.game_capture is None
    texts = [e.get("text", "") for _, e in state.bus.events_after(0)]
    assert "Page: http://127.0.0.1:6677/\n" in texts
    assert "\nCapture stopped (code 0).\n" in texts
    assert {"type": "finish", "kind": "game"} in [e for _, e in state.bus.events_after(0)]


def test_start_failure_ends_the_job(client, state, backend, monkeypatch):
    class Broken(FakeCapture):
        def start(self, on_line, on_exit):
            raise OSError("python not found")

    ready_settings()
    monkeypatch.setattr(game, "GameCaptureProcess", Broken)
    monkeypatch.setattr(web_jobs.threading, "Thread", SyncThread)
    post(client, "/api/game/start", {"language": "japanese"})
    events = [e for _, e in state.bus.events_after(0)]
    assert "python not found" in "".join(e.get("text", "") for e in events)
    assert events[-1] == {"type": "finish", "kind": "game"}
    assert state.game_capture is None and not state.running


def test_selection_is_locked_while_capturing(client, state, backend):
    ready_settings()
    state.game_capture = FakeCapture(Language.JAPANESE, None, False, "F9")
    assert post(client, "/api/game/area", {"area": "text", "region": [0, 0, 1, 1]}).status_code == 409
    assert post(client, "/api/game/window", {"id": 1}).status_code == 409
    assert client.get("/api/game/state").get_json()["running"] is True


def test_stop_terminates_the_subprocess(client, state, monkeypatch):
    monkeypatch.setattr(game.threading, "Thread", SyncThread)
    assert post(client, "/api/game/stop").get_json() == {"stopping": False}
    capture_process = FakeCapture(Language.JAPANESE, None, False, "F9")
    state.game_capture = capture_process
    assert post(client, "/api/game/stop").get_json() == {"stopping": True}
    assert capture_process.stopped


def test_language_tag_of_the_running_game(client, state, backend):
    state.game_capture, state.game_language = FakeCapture(Language.MANDARIN_TW, None, False, "F9"), "zh-Hant"
    assert client.get("/api/game/state").get_json()["language_tag"] == "zh-Hant"
    assert Language.CANTONESE_HK.profile.tag == "yue-Hant"
    assert Language.JAPANESE.profile.tag == "ja-JP"


def test_game_page(client):
    page = client.get("/game/")
    assert page.status_code == 200 and b"game.js" in page.data
