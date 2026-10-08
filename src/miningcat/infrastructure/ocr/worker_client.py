import json
import subprocess
import threading
from pathlib import Path

from miningcat.config.runtime import SRC_DIR, module_command
from miningcat.domain.languages import Language
from miningcat.infrastructure.ocr.worker import RESULT_PREFIX


class OcrWorkerError(RuntimeError):
    pass


class OcrWorker:
    """The OCR process (see worker.py), started on the first page read and kept for the next ones.
    One page at a time: it's restarted for another language, or when it died."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._language = None

    def read(self, language: Language, image: Path) -> dict:
        """{"width", "height", "lines": [[text, x, y, w, h]]} of an image."""
        with self._lock:
            for attempt in range(2):
                proc = self._ensure(language)
                try:
                    proc.stdin.write(f"{image}\n")
                    proc.stdin.flush()
                    answer = self._answer(proc, RESULT_PREFIX)
                except (OSError, OcrWorkerError):
                    self._stop()
                    if attempt:
                        raise OcrWorkerError("The text recognition stopped unexpectedly.")
                    continue
                if "error" in answer:
                    raise OcrWorkerError(f"The text of this page couldn't be read: {answer['error']}")
                return answer
        raise OcrWorkerError("The text recognition stopped unexpectedly.")

    def _ensure(self, language: Language) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None and self._language == language:
            return self._proc
        self._stop()
        self._proc = subprocess.Popen(
            module_command("miningcat.infrastructure.ocr.worker", language.id), cwd=str(SRC_DIR),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )
        self._language = language
        try:
            self._answer(self._proc, RESULT_PREFIX)  # {"ready": true}, once the engine is loaded
        except OcrWorkerError:
            self._stop()
            raise OcrWorkerError("The text recognition couldn't start (owocr needed: see `make install`).")
        return self._proc

    @staticmethod
    def _answer(proc: subprocess.Popen, prefix: str) -> dict:
        for line in proc.stdout:
            if line.startswith(prefix):
                return json.loads(line[len(prefix):])
        raise OcrWorkerError("The text recognition stopped unexpectedly.")

    def _stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._proc = None
        self._language = None
