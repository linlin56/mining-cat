import threading
import uuid
from pathlib import Path

from miningcat.application.mining.dictionaries.importer import import_dictionary


class ImportJobs:
    """Dictionary imports running in the background, followed by the settings page."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, path: Path, language: str, filename: str) -> str:
        """Imports the file (deleted afterwards) in a thread. Returns the id of the job."""
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "filename": filename, "progress": 0.0, "message": "Starting…",
                                  "done": False, "error": None, "dictionary": None}
        threading.Thread(target=self._run, args=(job_id, path, language, filename), daemon=True,
                         name=f"dict-import-{job_id}").start()
        return job_id

    def status(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _update(self, job_id: str, **values) -> None:
        with self._lock:
            self._jobs[job_id].update(**values)

    def _run(self, job_id: str, path: Path, language: str, filename: str) -> None:
        try:
            result = import_dictionary(
                path, language, lambda fraction, message: self._update(job_id, progress=round(fraction, 3), message=message),
                filename)
            self._update(job_id, done=True, progress=1.0, message="Imported", dictionary=result)
        except Exception as exc:
            self._update(job_id, done=True, error=str(exc), message="Failed")
        finally:
            path.unlink(missing_ok=True)


import_jobs = ImportJobs()


def start_import(path: Path, language: str, filename: str) -> str:
    return import_jobs.start(path, language, filename)


def job_status(job_id: str) -> dict | None:
    return import_jobs.status(job_id)
