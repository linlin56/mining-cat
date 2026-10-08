"""The events of the jobs (log lines, progress, start and end), followed by the page through Server-Sent Events:
reloading the page doesn't lose them."""
import itertools
import threading
from typing import Iterator

# Seconds between keep-alive comments on an idle event stream.
KEEPALIVE_SECONDS = 15


class EventBus:
    """Publish / subscribe: the jobs publish, every open page follows."""

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


