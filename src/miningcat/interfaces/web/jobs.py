"""The job the converter page runs (one at a time), and the server's state."""
import threading
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable

from miningcat.application.converter.jobs import Job, run_job
from miningcat.application.game_ocr.capture_process import GameCaptureProcess
from miningcat.infrastructure.system.updates import UpdateCheck
from miningcat.interfaces.web.discord_status import DiscordStatus
from miningcat.interfaces.web.event_bus import EventBus
from miningcat.interfaces.web.lan import LanListener
from miningcat.interfaces.web.process import ServerEnd


@dataclass
class JobSnapshot:
    running: bool = False
    kind: str | None = None
    status: str = ""
    pct: float = 0.0


class UpdateStatus(StrEnum):
    """How the home page's update goes (blueprints/updates.py; the same strings in home.js)."""

    NONE = ""
    UPDATING = "updating"
    RESTARTING = "restarting"
    FAILED = "failed"                  # the code didn't move: told once

    @property
    def busy(self) -> bool:
        """Whether no other update can start."""
        return self in (UpdateStatus.UPDATING, UpdateStatus.RESTARTING)


class JobBusyError(RuntimeError):
    pass


@dataclass
class AppState:
    bus: EventBus = field(default_factory=EventBus)
    last_video_srt: Path | None = None
    # The video game capture, while it runs (see blueprints/game.py)
    game_capture: GameCaptureProcess | None = None
    # BCP-47 tag of the game's language while it runs, for the /game/ page's dictionary popup
    game_language: str | None = None
    # The last previews: frames of a video for the subtitle region picker, a capture of the game for its areas.
    ocr_preview: dict = field(default_factory=lambda: {"frames": [], "version": 0})
    game_frame: dict = field(default_factory=lambda: {"data": None, "version": 0})
    # The user's Discord status, while the server runs (see discord_status.py)
    discord: DiscordStatus | None = None
    # The e-reader's door (see lan.py), made with the app
    lan: LanListener | None = None
    # The updates (see blueprints/updates.py): the last look for one and when (looked for under update_check_lock,
    # git and GitHub taking seconds), how the update goes (update_error: why it failed), under update_lock.
    update_check: UpdateCheck | None = None
    update_checked_at: float = 0.0
    update_check_lock: threading.Lock = field(default_factory=threading.Lock)
    update_status: UpdateStatus = UpdateStatus.NONE
    update_error: str = ""
    update_lock: threading.Lock = field(default_factory=threading.Lock)
    # Stops the server, saying why (to start again with the new code...). Set by app.main.
    stop_server: Callable[[ServerEnd], None] | None = None
    # This server's: the home page reloads once another one answers (started again after an update)
    server_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _job: JobSnapshot = field(default_factory=JobSnapshot)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._job.running

    def snapshot(self) -> dict:
        with self._lock:
            job = self._job
            return {
                "running": job.running,
                "kind": job.kind,
                "status": job.status,
                "pct": job.pct,
                # Events up to this id happened before the page loaded: replayed, but without dialogs.
                "last_event_id": self.bus.last_id,
                "last_video_srt": str(self.last_video_srt) if self.last_video_srt else None,
            }

    # The job's ProgressListener (called from its thread).

    def log(self, text: str) -> None:
        self.bus.publish({"type": "log", "text": text})

    def status(self, text: str, pct: float) -> None:
        with self._lock:
            self._job.status = text
            self._job.pct = pct
        self.bus.publish({"type": "status", "text": text, "pct": pct})

    # Writes a line in the log without belonging to a pipeline run (frequency lists, clear output...).
    def info(self, text: str) -> None:
        self.log(text)

    def start_job(self, job: Job, on_done: Callable[[object], None] = lambda result: None) -> None:
        """Runs a job in a background thread, reporting to the page; `on_done(result)` when it succeeded. Only one
        job runs at a time."""
        kind = job.kind
        with self._lock:
            if self._job.running:
                raise JobBusyError("A job is already running.")
            # Updated: the server stops in a moment, a job started now would be cut off
            if self.update_status is UpdateStatus.RESTARTING:
                raise JobBusyError("MiningCat is updated and starts again: wait for it.")
            self._job = JobSnapshot(running=True, kind=kind, status="Preparing…", pct=0)
        self.bus.reset()
        self.bus.publish({"type": "start", "kind": kind, "page": job.page})
        self.bus.publish({"type": "status", "text": "Preparing…", "pct": 0})

        def run() -> None:
            try:
                ok, result = run_job(job, self)
                if ok:
                    on_done(result)
            finally:
                with self._lock:
                    self._job.running = False
                self.bus.publish({"type": "finish", "kind": kind})

        threading.Thread(target=run, daemon=True, name=f"miningcat-{kind}").start()


def current_state() -> AppState:
    """The state of the server answering the request."""
    from flask import current_app

    return current_app.extensions["miningcat"]
