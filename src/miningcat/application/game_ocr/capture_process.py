import subprocess
import threading
from typing import Callable

from miningcat.application.converter.cli_command import CliCommand
from miningcat.domain.languages import Language
from miningcat.infrastructure.system import processes


class GameCaptureProcess:
    """`python -m miningcat game serve`, run by the GUIs until stopped: its output is passed on line by line, and
    `on_exit(returncode)` is called once it has ended, whatever the reason."""

    def __init__(self, language: Language, convert_target: str | None, continuous: bool, hotkey: str,
                 open_browser: bool = True):
        self.command = (
            CliCommand("game", "serve").option("--language", language.id)
            .flag("--no-browser", not open_browser)
            .option("--convert-to", convert_target)
            .flag("--continuous", continuous)
            .option("--hotkey", None if continuous else hotkey)
            .build()
        )
        self.proc: subprocess.Popen | None = None

    def start(self, on_line: Callable[[str], None], on_exit: Callable[[int], None]) -> subprocess.Popen:
        self.proc = processes.start(self.command)
        proc = self.proc

        def pump() -> None:
            for line in proc.stdout:
                on_line(line)
            on_exit(proc.wait())

        threading.Thread(target=pump, daemon=True).start()
        return proc

    def stop(self, timeout: float = 5) -> None:
        if self.proc is not None:
            processes.stop(self.proc, timeout)
