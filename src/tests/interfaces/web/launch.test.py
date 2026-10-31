"""The web GUI's launcher (__main__.py): the update at launch, the server's process, and the launcher started again
with the new code after an update."""
import os
import signal
import socket
import threading
from types import SimpleNamespace

import pytest

from miningcat.application import updates as app_updates
from miningcat.application import user_preferences
from miningcat.infrastructure.system import updates
from miningcat.interfaces.web import __main__ as web_main
from miningcat.interfaces.web import process, serve
from miningcat.interfaces.web.process import UP_TO_DATE_ENV, WATCH_PARENT, ServerEnd

AVAILABLE = updates.UpdateCheck("a" * 40, "b" * 40, ["fix: x"], 1)


@pytest.fixture(autouse=True)
def no_process(monkeypatch):
    """Never a real process, nor exec (it would replace pytest with MiningCat), nor a real SIGTERM handler."""
    monkeypatch.setattr(web_main.os, "execve", lambda *args: pytest.fail("exec"))
    monkeypatch.setattr(web_main.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("a process started"))
    monkeypatch.setattr(web_main.signal, "signal", lambda signum, handler: None)
    monkeypatch.delenv(web_main.UPDATED_ENV, raising=False)
    monkeypatch.setattr(web_main, "_child", None)


@pytest.fixture
def outcome(monkeypatch):
    """The outcome of the update at launch (update_now's), and the updates made."""
    state = SimpleNamespace(outcome=app_updates.UpdateOutcome(app_updates.Outcome.UPDATED, AVAILABLE), made=[])

    def update_now(say_up_to_date=True):
        state.made.append(1)
        return state.outcome

    monkeypatch.setattr(app_updates, "update_now", update_now)
    return state


def test_no_update_at_launch_by_default(outcome):
    assert web_main.update_at_launch() == (False, False) and outcome.made == []


@pytest.mark.parametrize("result, expected", [
    (app_updates.Outcome.UPDATED, (True, True)), (app_updates.Outcome.UP_TO_DATE, (False, True)),
    (app_updates.Outcome.OFF, (False, False)), (app_updates.Outcome.FAILED, (False, False)),  # the page looks again
])
def test_update_at_launch(outcome, result, expected):
    user_preferences.save_preferences({"updates": "launch"})
    outcome.outcome = app_updates.UpdateOutcome(result, AVAILABLE)
    assert web_main.update_at_launch() == expected


def test_no_update_at_launch_again_once_updated(outcome, monkeypatch):
    user_preferences.save_preferences({"updates": "launch"})
    monkeypatch.setenv(web_main.UPDATED_ENV, "1")
    assert web_main.update_at_launch() == (False, False) and outcome.made == []


def test_no_server_when_the_code_moved_without_its_packages(outcome):
    user_preferences.save_preferences({"updates": "launch"})
    outcome.outcome = app_updates.UpdateOutcome(app_updates.Outcome.INSTALL_FAILED, AVAILABLE)
    with pytest.raises(SystemExit, match="make gui"):
        web_main.update_at_launch()


def test_port_free():
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert not web_main.port_free(port)
    assert web_main.port_free(port)


class Relaunched(Exception):
    """relaunch replaces the process: it never returns."""


@pytest.fixture
def launch(monkeypatch, outcome):
    """main() with fake servers: each run returns the next of `codes`; the installs return `installs`."""
    fake = SimpleNamespace(codes=[], runs=[], installs=[], installed=[], port_free=True)
    monkeypatch.setattr(web_main, "port_free", lambda port: fake.port_free)
    monkeypatch.setattr(web_main, "run_server", lambda args, up_to_date: fake.runs.append((args, up_to_date))
                        or fake.codes.pop(0))
    monkeypatch.setattr(updates, "head", lambda: "a" * 40)
    monkeypatch.setattr(updates, "install_packages",
                        lambda old: fake.installed.append(old) or (fake.installs.pop(0) if fake.installs else 0))

    def relaunch(args):
        raise Relaunched(args)

    monkeypatch.setattr(web_main, "relaunch", relaunch)
    return fake


def test_the_server_stops(launch):
    launch.codes = [0]
    with pytest.raises(SystemExit) as exit_:
        web_main.main(["--port", "8080", "--reader"])
    assert exit_.value.code == 0
    assert launch.runs == [(["--port", "8080", "--page", "reader/"], False)] and launch.installed == []


def test_updated_at_launch_the_new_launcher_runs_the_server(launch):
    user_preferences.save_preferences({"updates": "launch"})
    with pytest.raises(Relaunched) as relaunched:
        web_main.main(["--port", "8080", "--player"])
    # The browser opens (no page yet); the new launcher knows it's up to date
    assert relaunched.value.args[0] == ["--port", "8080", "--player", "--up-to-date"]
    assert launch.runs == []


def test_the_new_launcher_knows_it_is_up_to_date(launch):
    launch.codes = [0]
    with pytest.raises(SystemExit):
        web_main.main(["--port", "8080", "--up-to-date"])
    assert launch.runs == [(["--port", "8080", "--page", ""], True)]


def test_updated_from_the_home_page_the_packages_then_the_new_launcher(launch, capsys):
    launch.codes = [ServerEnd.RESTART.value]
    with pytest.raises(Relaunched) as relaunched:
        web_main.main(["--port", "8080", "--reader"])
    # Installed with no server running, from the commit before the update; the page is open: no browser again
    assert launch.installed == ["a" * 40]
    assert relaunched.value.args[0] == ["--port", "8080", "--reader", "--no-browser"]
    assert "MiningCat starts again." in capsys.readouterr().out


def test_no_server_again_when_the_install_failed(launch, capsys):
    launch.codes, launch.installs = [ServerEnd.RESTART.value], [1]
    with pytest.raises(SystemExit, match="make gui"):
        web_main.main(["--port", "8080"])
    assert len(launch.runs) == 1 and "run make install" in capsys.readouterr().out


def test_port_taken_no_update(launch, outcome):
    user_preferences.save_preferences({"updates": "launch"})
    launch.port_free = False
    with pytest.raises(SystemExit, match="Port 8080 can't be opened"):
        web_main.main(["--port", "8080"])
    assert outcome.made == [] and launch.runs == []


class Child:
    """A process: wait() returns the next of `codes` (an exception is raised)."""

    def __init__(self, *codes):
        self.codes, self.terminated, self.started = list(codes), False, None

    def __call__(self, command, env, stdin):
        assert stdin is web_main.subprocess.PIPE  # it stops with this process
        self.started = (command, env)
        return self

    def wait(self):
        code = self.codes.pop(0)
        if isinstance(code, BaseException):
            raise code
        return code

    def poll(self):
        return None if self.codes else 0

    def terminate(self):
        self.terminated = True


def test_run_server(monkeypatch):
    child = Child(KeyboardInterrupt(), 0)  # Ctrl+C: the server stops on it, the launcher waits for it
    monkeypatch.setattr(web_main.subprocess, "Popen", child)
    monkeypatch.setenv(UP_TO_DATE_ENV, "1")
    assert web_main.run_server(["--port", "8080"], up_to_date=False) == 0
    command, env = child.started
    assert command == [web_main.sys.executable, "-m", "miningcat.interfaces.web.serve", "--port", "8080",
                       WATCH_PARENT]
    assert UP_TO_DATE_ENV not in env and str(web_main.SRC_DIR) in env["PYTHONPATH"]
    child = Child(0)
    monkeypatch.setattr(web_main.subprocess, "Popen", child)
    web_main.run_server([], up_to_date=True)
    assert child.started[1][UP_TO_DATE_ENV] == "1"


def test_run_server_killed(monkeypatch):
    monkeypatch.setattr(web_main.subprocess, "Popen", Child(-15))
    assert web_main.run_server([], up_to_date=False) == 143


def test_relaunch_with_exec(monkeypatch):
    class Exec(Exception):
        pass

    def execve(path, command, env):
        raise Exec(command, env)

    monkeypatch.setattr(web_main.os, "name", "posix")
    monkeypatch.setattr(web_main.os, "execve", execve)
    with pytest.raises(Exec) as started:
        web_main.relaunch(["--port", "8080"])
    command, env = started.value.args
    assert command == [web_main.sys.executable, "-m", "miningcat.interfaces.web", "--port", "8080"]
    assert env[web_main.UPDATED_ENV] == "1"


def test_relaunch_on_windows(monkeypatch):
    child = Child(0)
    monkeypatch.setattr(web_main.os, "name", "nt")
    monkeypatch.setattr(web_main.subprocess, "Popen", child)
    with pytest.raises(SystemExit) as exit_:
        web_main.relaunch(["--port", "8080"])
    assert exit_.value.code == 0
    assert child.started[0][-2:] == ["8080", WATCH_PARENT]  # it stops with this one


def test_sigterm(monkeypatch):
    child = Child(0)
    monkeypatch.setattr(web_main, "_child", child)
    web_main._on_sigterm(signal.SIGTERM, None)
    assert child.terminated  # the server stops, then this process
    monkeypatch.setattr(web_main, "_child", None)  # during an install: at once
    with pytest.raises(SystemExit) as exit_:
        web_main._on_sigterm(signal.SIGTERM, None)
    assert exit_.value.code == 143


def test_watch_parent(monkeypatch):
    read_end, write_end = os.pipe()
    monkeypatch.setattr(process, "STDIN", read_end)
    stopped = threading.Event()
    process.watch_parent(stopped.set)
    os.write(write_end, b"x")
    assert not stopped.wait(0.2)  # the parent is there
    os.close(write_end)  # gone
    assert stopped.wait(5)
    os.close(read_end)


def test_the_server_process(monkeypatch):
    calls = []
    monkeypatch.setattr(serve, "run_server", lambda **kwargs: calls.append(kwargs) or ServerEnd.RESTART)
    monkeypatch.delenv(UP_TO_DATE_ENV, raising=False)
    assert serve.main(["--port", "8080", "--page", "player/", "--no-browser", WATCH_PARENT]) == 3
    assert calls == [{"port": 8080, "open_browser": False, "page": "player/", "update_check": None,
                      "with_parent": True}]
    monkeypatch.setenv(UP_TO_DATE_ENV, "1")
    serve.main(["--port", "8080"])
    assert not calls[1]["update_check"].available and not calls[1]["with_parent"]
