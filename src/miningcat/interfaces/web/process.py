"""What the web GUI's two processes share (see __main__.py and serve.py), light: __main__.py loads no package that
an update may install again."""
import os
import threading
from enum import Enum

LAUNCHER_MODULE = "miningcat.interfaces.web"
SERVER_MODULE = "miningcat.interfaces.web.serve"
STDIN = 0
# The flag of a process started by another with stdin=PIPE: it stops with it (see watch_parent).
WATCH_PARENT = "--watch-parent"
# Set when MiningCat was found up to date at launch: the home page doesn't look again.
UP_TO_DATE_ENV = "MININGCAT_UP_TO_DATE"


class ServerEnd(Enum):
    """Why the server stopped: the exit code of its process."""

    STOPPED = 0     # Ctrl+C
    PORT_TAKEN = 1  # it never started
    RESTART = 3     # updated from the home page: to install the packages that changed, then start again


def port_taken(port: int) -> str:
    return f"Port {port} can't be opened: is MiningCat running already? Choose another port with make gui PORT=8080."


def watch_parent(stop) -> None:
    """Calls `stop()` once the process that started this one (with stdin=PIPE) is gone, however it went (killed,
    terminated on Windows): its end of the pipe closes."""
    def watch() -> None:
        # The file descriptor, not sys.stdin: its lock, held by this thread, would crash the interpreter's end.
        while os.read(STDIN, 4096):
            pass
        stop()

    threading.Thread(target=watch, daemon=True, name="miningcat-parent").start()
