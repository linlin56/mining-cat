"""The web GUI: `python -m miningcat.interfaces.web`. This process (the launcher) updates MiningCat at launch, when the
user chose it, then runs the server in a child (serve.py). After an update made from the home page, it installs the
packages that changed between two servers. It loads none of them, so pip can replace them, even on Windows. Once the
code moved, it starts again (the new launcher, with the new code) instead of running the new server itself."""
import argparse
import os
import signal
import socket
import subprocess
import sys

from miningcat.application import updates, user_preferences
from miningcat.config.runtime import SRC_DIR
from miningcat.infrastructure.system import updates as system_updates
from miningcat.interfaces.web.process import (
    LAUNCHER_MODULE,
    SERVER_MODULE,
    UP_TO_DATE_ENV,
    WATCH_PARENT,
    ServerEnd,
    port_taken,
    watch_parent,
)

DEFAULT_PORT = int(os.environ.get("MININGCAT_PORT", "5050"))
# Set in the launcher started again after an update: no update at launch again.
UPDATED_ENV = "MININGCAT_UPDATED"
# The process running now (the server, or the launcher started again on Windows): SIGTERM stops it too.
_child: subprocess.Popen | None = None


def port_free(port: int) -> bool:
    """Whether the server can listen on the port (another MiningCat may run there: no update under it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if os.name != "nt":  # as the server: a port just left (TIME_WAIT) can be taken again
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def update_at_launch() -> tuple[bool, bool]:
    """Updates MiningCat before the server starts, when the user chose it (Settings › User preferences). Returns
    whether the code moved, and whether it's up to date (the home page then doesn't look again). Stops when the code
    moved without its packages: the server wouldn't run right."""
    if os.environ.get(UPDATED_ENV) or user_preferences.get_preferences()["updates"] != "launch":
        return False, False
    outcome = updates.update_now(say_up_to_date=False)
    if outcome.outcome is updates.Outcome.INSTALL_FAILED:
        sys.exit(updates.START_AGAIN)
    return (outcome.outcome is updates.Outcome.UPDATED,
            outcome.outcome in (updates.Outcome.UPDATED, updates.Outcome.UP_TO_DATE))


def _env(**values: str) -> dict:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(SRC_DIR), os.environ.get("PYTHONPATH")]))}
    env.pop(UP_TO_DATE_ENV, None)
    return {**env, **values}


def _wait(child: subprocess.Popen) -> int:
    """Waits for a child started with stdin=PIPE (it stops with this process, see process.watch_parent). Returns its
    exit code."""
    global _child
    _child = child
    try:
        while True:
            try:
                code = child.wait()
            except KeyboardInterrupt:  # Ctrl+C reaches the child as well: it stops
                continue
            return 128 - code if code < 0 else code  # killed by a signal: the shell's convention
    finally:
        _child = None


def _on_sigterm(signum, frame) -> None:
    """Stopped by another process (tools/screenshots.py): the server too; during an install, at once."""
    if _child is not None and _child.poll() is None:
        _child.terminate()  # its end ends this process
    else:
        raise SystemExit(128 + signum)


def run_server(args: list[str], up_to_date: bool) -> int:
    """Runs the server's process until it stops. Returns its exit code."""
    env = _env(**({UP_TO_DATE_ENV: "1"} if up_to_date else {}))
    return _wait(subprocess.Popen([sys.executable, "-m", SERVER_MODULE, *args, WATCH_PARENT], env=env,
                                  stdin=subprocess.PIPE))


def relaunch(args: list[str]) -> None:
    """Starts the launcher again, with the new code (the same arguments `args`), in place of this one."""
    command = [sys.executable, "-m", LAUNCHER_MODULE, *args]
    env = _env(**{UPDATED_ENV: "1"})
    sys.stdout.flush()
    if os.name != "nt":
        os.execve(sys.executable, command, env)
    # Windows has no exec: the new launcher runs in a child (light: it loads no package), stopping with this one.
    sys.exit(_wait(subprocess.Popen([*command, WATCH_PARENT], env=env, stdin=subprocess.PIPE)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MiningCat web GUI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"local port (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--reader", action="store_true", help="open the ebook reader instead of the converter")
    parser.add_argument("--player", action="store_true", help="open the video player instead of the converter")
    parser.add_argument("--up-to-date", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(WATCH_PARENT, action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_sigterm)
    if args.watch_parent:
        watch_parent(lambda: os.kill(os.getpid(), signal.SIGTERM) if _child is None else _child.terminate())
    if not port_free(args.port):
        sys.exit(port_taken(args.port))
    launch_args = ["--port", str(args.port), *(["--reader"] if args.reader else []),
                   *(["--player"] if args.player else [])]
    moved, up_to_date = update_at_launch()
    if moved:
        relaunch([*launch_args, *(["--no-browser"] if args.no_browser else []), "--up-to-date"])
    page = "reader/" if args.reader else "player/" if args.player else ""
    try:
        old = system_updates.head()
    except system_updates.UpdateError:
        old = ""
    server_args = ["--port", str(args.port), "--page", page, *(["--no-browser"] if args.no_browser else [])]
    code = run_server(server_args, up_to_date or args.up_to_date)
    if code != ServerEnd.RESTART.value:
        sys.exit(code)
    # Updated from the home page: the code moved, its packages next, then the new launcher (the page is open: no
    # browser again; it looks for an update again).
    if not old or system_updates.install_packages(old) != 0:
        print(updates.INSTALL_FAILED, flush=True)
        sys.exit(updates.START_AGAIN)
    print("MiningCat starts again.", flush=True)
    relaunch([*launch_args, "--no-browser"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # during an update
        sys.exit(130)
