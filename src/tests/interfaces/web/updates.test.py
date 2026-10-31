import time
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

from miningcat.infrastructure.system import updates
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.blueprints import updates as updates_bp
from miningcat.interfaces.web.blueprints.updates import UpdateJob
from miningcat.interfaces.web.jobs import AppState, JobBusyError, UpdateStatus
from miningcat.interfaces.web import process
from miningcat.interfaces.web.process import ServerEnd

HEADERS = {"X-MiningCat": "1"}
AVAILABLE = updates.UpdateCheck("a" * 40, "b" * 40, ["fix: x", "feat: y"], 2)


@pytest.fixture
def state():
    state = AppState()
    state.stops = []
    state.stop_server = state.stops.append
    return state


@pytest.fixture
def client(state):
    app = web_app.create_app(state)
    app.testing = True
    return app.test_client()


@pytest.fixture
def checks(monkeypatch):
    """The checks made: each returns the next of `answers` (AVAILABLE by default)."""
    made, answers = [], []

    def check():
        made.append(1)
        return answers.pop(0) if answers else AVAILABLE

    monkeypatch.setattr(updates, "check", check)
    return made, answers


@pytest.fixture
def updated(monkeypatch):
    """The updates made, and their result (an UpdateResult, or an exception raised)."""
    made = {"checks": [], "result": updates.UpdateResult(2)}

    def update(check, install=True):
        assert not install  # after the server stops (__main__.py)
        made["checks"].append(check)
        if isinstance(made["result"], Exception):
            raise made["result"]
        return made["result"]

    monkeypatch.setattr(updates, "update", update)
    return made


def wait_for_the_job(state):
    for _ in range(200):
        if not state.running:
            return
        time.sleep(0.01)
    pytest.fail("the update job doesn't end")


def test_the_check_is_kept_a_while(client, state, checks):
    assert client.get("/api/update").get_json() == {"available": True, "current": "aaaaaaa", "target": "bbbbbbb",
                                                    "commits": 2, "changes": ["fix: x", "feat: y"], "off": "",
                                                    "error": "", "status": "", "server": state.server_id}
    client.get("/api/update")
    assert len(checks[0]) == 1
    state.update_checked_at -= updates_bp.CHECK_TTL_S + 1
    client.get("/api/update")
    assert len(checks[0]) == 2


@pytest.mark.parametrize("failed", [updates.UpdateCheck(error="GitHub can't be reached: offline"),
                                    updates.UpdateCheck(off="git isn't installed (or not in the PATH).")])
def test_a_failed_check_is_made_again_sooner(client, state, checks, failed):
    checks[1].append(failed)
    assert not client.get("/api/update").get_json()["available"]
    state.update_checked_at -= updates_bp.OFF_TTL_S + 1
    assert client.get("/api/update").get_json()["available"]


@pytest.fixture
def server(monkeypatch):
    """app.main without its server: `run(state)` stands for its serve_forever (until it stops); the timers it starts
    are recorded, not started."""
    class Presence:
        available = True

        def __init__(self, client_id):
            pass

        def start(self):
            Presence.started.append(self)

        def stop(self):
            pass

    fake = SimpleNamespace(run=lambda state: None, timers=[])

    class Server:
        def __init__(self, app):
            self.app = app

        def serve_forever(self):
            fake.run(self.app.extensions["miningcat"])

        def shutdown(self):
            pass

    monkeypatch.setattr(web_app, "DiscordPresence", Presence)
    monkeypatch.setattr(web_app.LanListener, "apply", lambda self, config: None)
    monkeypatch.setattr(web_app.threading, "Timer",
                        lambda delay, function: fake.timers.append(function) or SimpleNamespace(start=lambda: None))
    def make_server(host, port, app, threaded):
        if fake.port_taken:
            raise OSError(48, "Address already in use")
        fake.servers.append(Server(app))
        return fake.servers[-1]

    monkeypatch.setattr(web_app, "make_server", make_server)
    fake.servers, fake.port_taken = [], False
    fake.presences = Presence.started = []
    return fake


def test_the_check_made_at_launch_is_kept(server, checks):
    def run(state):
        with state.update_lock:
            assert updates_bp._check(state) is AVAILABLE

    server.run = run
    assert web_app.main(open_browser=False, update_check=AVAILABLE) is ServerEnd.STOPPED
    assert checks[0] == []


def test_port_taken(server, capsys):
    server.port_taken = True
    assert web_app.main(port=5050, open_browser=False) is ServerEnd.PORT_TAKEN
    assert capsys.readouterr().out == f"{process.port_taken(5050)} (Address already in use)\n"
    assert server.presences == []  # nothing started


def test_the_server_stops_to_start_again(server):
    server.run = lambda state: state.stop_server(ServerEnd.RESTART)
    assert web_app.main(open_browser=False) is ServerEnd.RESTART
    assert server.timers == [server.servers[0].shutdown]


def test_update_then_start_again(client, state, checks, updated):
    client.get("/api/update")
    answer = {"status": "updating", "server": state.server_id}
    assert client.post("/api/update", json={}, headers=HEADERS).get_json() == answer
    wait_for_the_job(state)
    # To the commit the page offered: looked for a moment ago
    assert len(checks[0]) == 1 and updated["checks"] == [AVAILABLE]
    assert state.stops == [ServerEnd.RESTART]
    assert client.get("/api/update").get_json() == {"status": "restarting", "error": "", "server": state.server_id}
    # Not twice
    assert client.post("/api/update", json={}, headers=HEADERS).get_json()["status"] == "restarting"
    assert len(updated["checks"]) == 1


def test_an_old_check_is_made_again_before_updating(client, state, checks, updated):
    client.get("/api/update")
    state.update_checked_at -= updates_bp.FRESH_S + 1
    client.post("/api/update", json={}, headers=HEADERS)
    wait_for_the_job(state)
    assert len(checks[0]) == 2


def test_no_update_anymore(client, state, checks, updated):
    """Up to date since the page looked (updated from the terminal...)."""
    client.get("/api/update")
    checks[1].append(updates.UpdateCheck("b" * 40, "b" * 40))
    state.update_checked_at -= updates_bp.FRESH_S + 1
    client.post("/api/update", json={}, headers=HEADERS)
    wait_for_the_job(state)
    # Not an error: no banner anymore
    assert client.get("/api/update").get_json()["status"] == ""
    assert updated["checks"] == [] and state.stops == []


def test_a_new_server_has_another_id():
    assert AppState().server_id != AppState().server_id


@pytest.mark.parametrize("error", [updates.UpdateError("The code changed since the check: check again."),
                                   PermissionError("The code changed since the check: check again.")])
def test_update_failed(client, state, checks, updated, error):
    updated["result"] = error
    client.post("/api/update", json={}, headers=HEADERS)
    wait_for_the_job(state)
    assert client.get("/api/update").get_json() == {"status": "failed", "server": state.server_id,
                                                    "error": "The code changed since the check: check again."}
    # Told once, then looked for again; it can be tried again
    assert client.get("/api/update").get_json()["status"] == ""
    assert state.stops == []
    assert client.post("/api/update", json={}, headers=HEADERS).get_json()["status"] == "updating"


def test_no_job_starts_while_the_server_stops_to_start_again(client, state, checks, updated):
    client.post("/api/update", json={}, headers=HEADERS)
    wait_for_the_job(state)
    with pytest.raises(JobBusyError, match="starts again"):
        state.start_job(UpdateJob(state))


def test_a_long_check_does_not_hold_the_status(client, state, checks):
    """Looking for an update (seconds) holds update_check_lock: the status is told meanwhile."""
    with state.update_check_lock:
        state.update_status = UpdateStatus.RESTARTING
        assert client.get("/api/update").get_json()["status"] == "restarting"


def test_no_update_while_a_job_runs(client, state, checks, updated):
    state._job.running = True
    res = client.post("/api/update", json={}, headers=HEADERS)
    assert res.status_code == 409 and res.get_json()["title"] == "Busy"
    assert updated["checks"] == [] and state.update_status == ""


def test_update_needs_the_header(client, checks, updated):
    assert client.post("/api/update", json={}).status_code == 403
    assert updated["checks"] == []


def test_the_home_page_has_the_banner(client):
    assert 'id="update"' in client.get("/").get_data(as_text=True)
