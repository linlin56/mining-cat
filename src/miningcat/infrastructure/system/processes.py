import os
import subprocess
from typing import Callable

from miningcat.config.runtime import SRC_DIR


def start(args: list[str]) -> subprocess.Popen:
    """Starts a process of the app (from SRC_DIR), its output (stdout and stderr) read line by line as text."""
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(SRC_DIR),
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
        encoding="utf-8",
    )


def run(args: list[str], on_line: Callable[[str], None]) -> int:
    """Runs a process of the app until it ends, passing each line of its output on. Returns its exit code."""
    proc = start(args)
    for line in proc.stdout:
        on_line(line)
    proc.wait()
    return proc.returncode


def stop(proc: subprocess.Popen, timeout: float = 5) -> None:
    """SIGTERM lets the process shut down cleanly; it's killed if it doesn't in time."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
