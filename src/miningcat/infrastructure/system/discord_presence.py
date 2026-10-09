"""Discord Rich Presence: what the user does in MiningCat, shown on their Discord profile.

Discord's desktop app is reached through its local socket (pypresence). It may be closed, opened later, or not
installed at all: a thread keeps trying to connect, and MiningCat works the same without it.
"""
import threading
import time
from dataclasses import dataclass

try:
    from pypresence import Presence
    from pypresence.exceptions import PyPresenceException
except ImportError:  # pragma: no cover - pypresence is in requirements.txt
    Presence = None
    PyPresenceException = Exception

# A closed Discord is looked for again every 15 seconds.
UPDATE_INTERVAL = 15.0
# The changes made within this delay (pages opened one after the other) are sent as one update.
COALESCE_DELAY = 1.0


@dataclass(frozen=True)
class Activity:
    details: str            # first line, e.g. "Reading a book"
    state: str = ""         # second line, e.g. "Studying Japanese"
    large_image: str = ""   # the key of an image uploaded in the Discord application's Rich Presence assets
    large_text: str = ""


class DiscordPresence:
    def __init__(self, client_id: str, connect=None, interval: float = UPDATE_INTERVAL):
        self.client_id = client_id
        self._connect = connect or (self._pypresence_client if Presence is not None else None)
        self._interval = interval
        self._started_at = int(time.time())
        self._wanted: Activity | None = None
        self._shown: Activity | None = None
        self._client = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return bool(self.client_id) and self._connect is not None

    def start(self) -> None:
        if not self.available or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="discord-presence", daemon=True)
        self._thread.start()

    def show(self, activity: Activity | None) -> None:
        """The activity to show (None: none); sent by the thread, never blocks the caller."""
        with self._lock:
            self._wanted = activity
        self._wake.set()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._disconnect()

    def _pypresence_client(self):
        client = Presence(self.client_id)
        # connect() makes its own event loop: closed here, and on failure, so that retrying doesn't leak them.
        client.loop.close()
        try:
            client.connect()
        except BaseException:
            if client.sock_writer is not None:
                client.sock_writer.close()
                client.loop.run_until_complete(client.sock_writer.wait_closed())
            client.loop.close()
            raise
        return client

    def _run(self) -> None:
        while not self._stopping.is_set():
            self.sync()
            if self._wake.wait(self._interval):
                self._stopping.wait(COALESCE_DELAY)
                self._wake.clear()

    def sync(self) -> None:
        """Connects if needed and sends the wanted activity, if it isn't the one shown."""
        with self._lock:
            wanted = self._wanted
        if self._client is None:
            try:
                self._client = self._connect()
            except (PyPresenceException, OSError, RuntimeError):
                return  # Discord isn't running: tried again later
            self._shown = None
        if wanted == self._shown:
            return
        try:
            if wanted is None:
                self._client.clear()
            else:
                self._client.update(details=wanted.details, state=wanted.state or None, start=self._started_at,
                                    large_image=wanted.large_image or None, large_text=wanted.large_text or None)
            self._shown = wanted
        except (PyPresenceException, OSError, RuntimeError):
            self._disconnect()  # Discord was closed: connected again later

    def _disconnect(self) -> None:
        client, self._client, self._shown = self._client, None, None
        if client is not None:
            try:
                client.close()
            except (PyPresenceException, OSError, RuntimeError):
                pass
