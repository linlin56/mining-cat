import pytest

from miningcat.infrastructure.system import updates
from miningcat.interfaces.cli.main import main

AVAILABLE = updates.UpdateCheck("a" * 40, "b" * 40, ["fix: x"], 1)


@pytest.fixture
def fake(monkeypatch):
    """The check's answer, and the updates made (their result: `result`, or an exception raised)."""
    state = {"check": AVAILABLE, "result": updates.UpdateResult(1), "updated": []}
    monkeypatch.setattr(updates, "check", lambda: state["check"])

    def update(check, install=True):
        state["updated"].append(check)
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(updates, "update", update)
    return state


def test_check_only(fake, capsys):
    main(["update", "--check"])
    assert capsys.readouterr().out == "An update is available (1 new commit):\n  - fix: x\n"
    assert fake["updated"] == []


def test_update(fake, capsys):
    main(["update"])
    assert fake["updated"] == [AVAILABLE]
    assert capsys.readouterr().out.endswith("MiningCat is updated to bbbbbbb.\n")


def test_updates_off_is_not_a_failure(fake):
    fake["check"] = updates.UpdateCheck(off="git isn't installed (or not in the PATH).")
    main(["update"])  # no SystemExit: `make update && make gui` goes on


@pytest.mark.parametrize("result", [updates.UpdateError("git merge failed: no"), updates.UpdateResult(1, 1)])
def test_a_failed_update_exits_with_1(fake, result):
    fake["result"] = result
    with pytest.raises(SystemExit) as exit_:
        main(["update"])
    assert exit_.value.code == 1


def test_a_failed_check_exits_with_1(fake, capsys):
    fake["check"] = updates.UpdateCheck(error="GitHub can't be reached: offline")
    with pytest.raises(SystemExit) as exit_:
        main(["update"])
    assert exit_.value.code == 1


def test_a_failed_check_with_check_only_exits_with_1(fake, capsys):
    fake["check"] = updates.UpdateCheck(error="GitHub can't be reached: offline")
    with pytest.raises(SystemExit) as exit_:
        main(["update", "--check"])
    assert exit_.value.code == 1
    assert capsys.readouterr().out == "Can't look for an update: GitHub can't be reached: offline\n"


def test_python_m_miningcat_update_loads_no_other_command(fake, monkeypatch):
    """pip can then replace the packages the rest of the CLI loads (Windows locks them)."""
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["python -m miningcat", "update", "--check"])
    monkeypatch.delitem(sys.modules, "miningcat.interfaces.cli.main", raising=False)
    runpy.run_module("miningcat", run_name="__main__")
    assert "miningcat.interfaces.cli.main" not in sys.modules
