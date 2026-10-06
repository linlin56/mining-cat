import itertools
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

# Seconds between keep-alive comments on an idle event stream.
KEEPALIVE_SECONDS = 15


class EventBus:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._events: list[tuple[int, dict]] = []
        self._ids = itertools.count(1)
        self._closed = False

    # Forgets past events (a new job starts with an empty log) while keeping ids increasing,
    # so that a browser resuming with an old Last-Event-ID receives the whole new job.
    def reset(self) -> None:
        with self._cond:
            self._events = []

    def publish(self, event: dict) -> int:
        with self._cond:
            event_id = next(self._ids)
            self._events.append((event_id, event))
            self._cond.notify_all()
            return event_id

    @property
    def last_id(self) -> int:
        with self._cond:
            return self._events[-1][0] if self._events else 0

    def events_after(self, last_id: int) -> list[tuple[int, dict]]:
        with self._cond:
            return [(i, e) for i, e in self._events if i > last_id]

    # Yields (id, event) pairs newer than last_id as they arrive, or None every
    # `keepalive` seconds of inactivity so that the caller can keep the connection alive.
    def follow(self, last_id: int, keepalive: float = KEEPALIVE_SECONDS) -> Iterator[tuple[int, dict] | None]:
        while True:
            with self._cond:
                pending = [(i, e) for i, e in self._events if i > last_id]
                if not pending and not self._closed:
                    self._cond.wait(timeout=keepalive)
                    pending = [(i, e) for i, e in self._events if i > last_id]
                closed = self._closed
            if not pending:
                if closed:
                    return
                yield None
                continue
            for item in pending:
                last_id = item[0]
                yield item

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


@dataclass
class JobSnapshot:
    running: bool = False
    kind: str | None = None
    status: str = ""
    pct: float = 0.0


class JobBusyError(RuntimeError):
    pass


@dataclass
class AppState:
    bus: EventBus = field(default_factory=EventBus)
    last_video_srt: Path | None = None
    # `main.py game serve` subprocess, while the video game capture runs (see web/game.py)
    game_proc: subprocess.Popen | None = None
    # BCP-47 tag of the game's language while it runs, for the /game/ page's dictionary popup
    game_language: str | None = None
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

    # --- callbacks handed to the pipeline (called from the worker thread) ---

    def log(self, text: str) -> None:
        self.bus.publish({"type": "log", "text": text})

    def set_status(self, text: str, pct: float) -> None:
        with self._lock:
            self._job.status = text
            self._job.pct = pct
        self.bus.publish({"type": "status", "text": text, "pct": pct})

    # Writes a line in the log without belonging to a pipeline run (frequency lists, clear output...).
    def info(self, text: str) -> None:
        self.log(text)

    # Runs `target(**kwargs, schedule=..., log=..., set_status=..., on_done=..., on_finish=...)`
    # in a background thread. Only one pipeline runs at a time, like in the Tkinter GUI.
    def start_job(self, kind: str, target: Callable, on_done: Callable, **kwargs) -> None:
        with self._lock:
            if self._job.running:
                raise JobBusyError("A job is already running.")
            self._job = JobSnapshot(running=True, kind=kind, status="Preparing…", pct=0)
        self.bus.reset()
        self.bus.publish({"type": "start", "kind": kind})
        self.bus.publish({"type": "status", "text": "Preparing…", "pct": 0})

        def schedule(_delay, fn, *args):
            fn(*args)

        def on_finish() -> None:
            with self._lock:
                self._job.running = False
            self.bus.publish({"type": "finish", "kind": kind})

        def run() -> None:
            try:
                target(
                    **kwargs,
                    schedule=schedule,
                    log=self.log,
                    set_status=self.set_status,
                    on_done=on_done,
                    on_finish=on_finish,
                )
            except Exception as exc:  # the pipeline catches its own errors; this is a last resort
                self.log(f"\n[ERROR] {exc}\n")
                on_finish()

        threading.Thread(target=run, daemon=True, name=f"miningcat-{kind}").start()
