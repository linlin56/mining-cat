from dataclasses import dataclass
from enum import Enum
from typing import Callable

from miningcat.infrastructure.system import updates


class Outcome(Enum):
    # the clone can't update on its own (check.off says why)
    OFF = "off"
    UP_TO_DATE = "up to date"
    UPDATED = "updated"
    # the code didn't move, or the look for an update failed (error says why)
    # the code moved, without its packages: `make install`
    FAILED = "failed"
    INSTALL_FAILED = "install failed"

    @property
    def code_changed(self) -> bool:
        return self in (Outcome.UPDATED, Outcome.INSTALL_FAILED)


@dataclass(frozen=True)
class UpdateOutcome:
    outcome: Outcome
    check: updates.UpdateCheck
    error: str = ""


INSTALL_FAILED = "MiningCat is updated, but installing its packages failed (see pip's output in the terminal): run make install."
# After INSTALL_FAILED: the server isn't running (neither the old code nor the new one would run right).
START_AGAIN = "Then start MiningCat again (make gui)."


def commits(n: int) -> str:
    return f"{n} new commit{'s' * (n > 1)}"


def describe(check: updates.UpdateCheck, changes: bool = False) -> list[str]:
    """Where the clone stands, in lines; `changes`: with the subjects of the new commits."""
    if check.off:
        return [f"Updates off: {check.off}"]
    if check.error:
        return [f"Can't look for an update: {check.error}"]
    if not check.available:
        return ["MiningCat is up to date."]
    lines = [f"An update is available ({commits(check.commits)})" + (":" if changes else ".")]
    return lines + [f"  - {subject}" for subject in check.changes] if changes else lines


def update_now(say: Callable[[str], None] = print, say_up_to_date: bool = True,
               check: updates.UpdateCheck | None = None, install: bool = True) -> UpdateOutcome:
    """Updates MiningCat when a newer commit passed the CI (`check`: a look for it just made, else made here),
    telling how it goes with `say`. Not `install`: only the code moves, the caller installs the packages (with
    updates.install_packages, once no process uses them)."""
    check = check or updates.check()
    if not check.available:
        if check.off or check.error or say_up_to_date:
            for line in describe(check):
                say(line)
        if check.error:
            return UpdateOutcome(Outcome.FAILED, check, describe(check)[0])
        return UpdateOutcome(Outcome.OFF if check.off else Outcome.UP_TO_DATE, check)
    say(f"Updating MiningCat ({commits(check.commits)})…")
    try:
        result = updates.update(check, install)
    except updates.UpdateError as exc:
        say(f"Update failed: {exc}")
        return UpdateOutcome(Outcome.FAILED, check, str(exc))
    if result.returncode != 0:
        say(INSTALL_FAILED)
        return UpdateOutcome(Outcome.INSTALL_FAILED, check, INSTALL_FAILED)
    say(f"MiningCat is updated to {check.target[:7]}.")
    return UpdateOutcome(Outcome.UPDATED, check)
