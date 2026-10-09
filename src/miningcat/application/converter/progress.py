from typing import Protocol


class ProgressListener(Protocol):
    """Follows a job of the converter: the web GUI publishes it to the page, PrintProgress to the terminal."""

    def log(self, text: str) -> None:
        """A piece of the job's log (the output of its steps)."""

    def status(self, text: str, pct: float) -> None:
        """The step the job is at, and its progress (0-100)."""


class PrintProgress:
    """A ProgressListener writing to the terminal."""

    def log(self, text: str) -> None:
        print(text, end="")

    def status(self, text: str, pct: float) -> None:
        print(f"[{pct:.0f}%] {text}")
