"""The updates of MiningCat, offered by the home page: a look for a newer commit of main whose tests passed, and the
update (see infrastructure/system/updates.py). The update is a job (none of the converter's, nor an install, runs
meanwhile); then the server stops, the packages that changed are installed, and another server starts with the new
code (__main__.py), the home page asking how it goes until it answers."""
import time

from flask import Blueprint, jsonify

from miningcat.application import updates as app_updates
from miningcat.application.converter.jobs import Job
from miningcat.application.converter.progress import ProgressListener
from miningcat.infrastructure.system import updates
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import AppState, JobBusyError, UpdateStatus, current_state
from miningcat.interfaces.web.process import ServerEnd

bp = Blueprint("updates", __name__)

# How long a look for an update holds (git fetch and GitHub take a few seconds); one that failed (offline...) or found
# updates off, less.
CHECK_TTL_S = 3600
OFF_TTL_S = 300
# The update goes to the commit the page offered when it was looked for this recently, else looks again.
FRESH_S = 300


class UpdateJob(Job):
    """Moves the code to the newest commit whose tests passed, then stops the server: __main__.py installs the
    packages that changed (no server using them: Windows wouldn't let pip replace them), then starts it again."""

    kind, page = "update", "home"

    def __init__(self, state: AppState):
        self.state = state

    def _end(self, status: UpdateStatus, error: str = "") -> None:
        with self.state.update_lock:
            self.state.update_status, self.state.update_error = status, error
        with self.state.update_check_lock:
            self.state.update_check = None

    def run(self, listener: ProgressListener) -> None:
        listener.status("Updating MiningCat (see the terminal)…", 10)

        def say(line: str) -> None:
            print(line)
            listener.log(line + "\n")

        try:
            outcome = app_updates.update_now(say, check=_check(self.state, FRESH_S), install=False)
        except Exception as exc:  # whatever it is, the page is told and can try again
            self._end(UpdateStatus.FAILED, str(exc))
            raise
        if outcome.outcome is app_updates.Outcome.UP_TO_DATE:  # updated meanwhile (git pull...): no banner
            self._end(UpdateStatus.NONE)
            return
        if outcome.outcome is not app_updates.Outcome.UPDATED:  # failed, or updates off since
            self._end(UpdateStatus.FAILED, outcome.error or app_updates.describe(outcome.check)[0])
            raise updates.UpdateError(self.state.update_error)
        self._end(UpdateStatus.RESTARTING)
        listener.status("Done", 100)
        if self.state.stop_server is not None:
            self.state.stop_server(ServerEnd.RESTART)


def _check(state: AppState, ttl_s: float | None = None) -> updates.UpdateCheck:
    """The last look for an update, looked for again once older than `ttl_s` (by default: CHECK_TTL_S, OFF_TTL_S
    when it failed). The other requests don't wait for it: it holds update_check_lock, not update_lock."""
    with state.update_check_lock:
        check = state.update_check
        if ttl_s is None:
            ttl_s = OFF_TTL_S if check is not None and (check.off or check.error) else CHECK_TTL_S
        if check is None or time.monotonic() - state.update_checked_at > ttl_s:
            state.update_check, state.update_checked_at = updates.check(), time.monotonic()
        return state.update_check


@bp.get("/api/update")
def api_update():
    """Whether an update is available, or how the update goes."""
    state = current_state()
    with state.update_lock:
        status, error = state.update_status, state.update_error
        if status is UpdateStatus.FAILED:  # told once
            state.update_status, state.update_error = UpdateStatus.NONE, ""
    if status is not UpdateStatus.NONE:
        return jsonify(status=status, error=error, server=state.server_id)
    return jsonify({**_check(state).to_dict(), "status": status, "server": state.server_id})


@bp.post("/api/update")
def api_run_update():
    state = current_state()
    with state.update_lock:
        if not state.update_status.busy:
            try:
                state.start_job(UpdateJob(state))
            except JobBusyError:
                raise UserError("Busy", "Wait for the job of the converter (or the install) to end before updating.",
                                409)
            state.update_status, state.update_error = UpdateStatus.UPDATING, ""
        return jsonify(status=state.update_status, server=state.server_id)
