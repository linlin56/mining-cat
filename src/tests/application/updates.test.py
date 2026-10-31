import pytest

from miningcat.application import updates as app_updates
from miningcat.infrastructure.system import updates

AVAILABLE = updates.UpdateCheck("a" * 40, "b" * 40, ["fix: x"], 1)
Outcome = app_updates.Outcome


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


def run(**kwargs):
    said = []
    return app_updates.update_now(said.append, **kwargs), said


def test_update(fake):
    assert run() == (app_updates.UpdateOutcome(Outcome.UPDATED, AVAILABLE),
                     ["Updating MiningCat (1 new commit)…", "MiningCat is updated to bbbbbbb."])
    assert fake["updated"] == [AVAILABLE]


def test_up_to_date(fake):
    fake["check"] = updates.UpdateCheck("a" * 40, "a" * 40)
    assert run() == (app_updates.UpdateOutcome(Outcome.UP_TO_DATE, fake["check"]), ["MiningCat is up to date."])
    assert run(say_up_to_date=False)[1] == [] and fake["updated"] == []


def test_updates_off_are_told_all_the_same(fake):
    fake["check"] = updates.UpdateCheck(off="git isn't installed (or not in the PATH).")
    outcome, said = run(say_up_to_date=False)
    assert outcome.outcome is Outcome.OFF and not outcome.outcome.code_changed
    assert said == ["Updates off: git isn't installed (or not in the PATH)."]


def test_update_failed(fake):
    fake["result"] = updates.UpdateError("git merge failed: no")
    outcome, said = run()
    assert outcome == app_updates.UpdateOutcome(Outcome.FAILED, AVAILABLE, "git merge failed: no")
    assert said[-1] == "Update failed: git merge failed: no" and not outcome.outcome.code_changed


def test_install_failed(fake):
    fake["result"] = updates.UpdateResult(1, returncode=1)
    outcome, said = run()
    assert outcome.outcome is Outcome.INSTALL_FAILED and outcome.outcome.code_changed
    assert "make install" in outcome.error and said[-1] == outcome.error


def test_a_failed_check_is_a_failure(fake):
    fake["check"] = updates.UpdateCheck(error="GitHub can't be reached: offline")
    outcome, said = run(say_up_to_date=False)
    assert outcome == app_updates.UpdateOutcome(Outcome.FAILED, fake["check"],
                                                "Can't look for an update: GitHub can't be reached: offline")
    assert said == [outcome.error] and fake["updated"] == []


def test_the_check_given_is_used(fake, monkeypatch):
    monkeypatch.setattr(updates, "check", lambda: pytest.fail("looked for again"))
    assert run(check=AVAILABLE)[0].outcome is Outcome.UPDATED


def test_describe():
    assert app_updates.describe(AVAILABLE) == ["An update is available (1 new commit)."]
    two = updates.UpdateCheck("a" * 40, "b" * 40, ["fix: x", "feat: y"], 2)
    assert app_updates.describe(two, changes=True) == ["An update is available (2 new commits):", "  - fix: x",
                                                       "  - feat: y"]
