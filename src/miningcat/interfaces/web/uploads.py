"""Files picked in the browser: a browser can't give a file's path, so they're uploaded to sources/.staging/, then the
pipeline copies them where it needs them. The page refers to files by their path under the project's root."""
import shutil
from pathlib import Path

from werkzeug.utils import secure_filename

from miningcat.application.converter import source_files
from miningcat.config.paths import paths

KINDS = ("audio", "ebook", "video")


class InvalidPathError(ValueError):
    pass


def staging_dir(kind: str) -> Path:
    if kind not in KINDS:
        raise InvalidPathError(f"Unknown file kind: {kind!r}")
    return paths.staging / kind


def clear_staging() -> None:
    if paths.staging.exists():
        shutil.rmtree(paths.staging, ignore_errors=True)


def describe(path: Path) -> dict:
    return {"path": paths.to_ref(path), "name": path.name}


def resolve_ref(ref: str, base: Path | None = None, must_exist: bool = True) -> Path:
    """A path sent by the browser back into a Path, refusing anything outside `base` (sources/ by default): the
    browser only ever gets paths the server gave it, but nothing should be trusted."""
    base = base or paths.sources
    if not isinstance(ref, str) or not ref:
        raise InvalidPathError("Missing file path.")
    path = (paths.root / ref).resolve()
    if not path.is_relative_to(base.resolve()):
        raise InvalidPathError(f"Path outside of {base.name}/: {ref}")
    if must_exist and not path.is_file():
        raise InvalidPathError(f"File not found: {ref} (it may have been removed, pick it again)")
    return path


def resolve_refs(refs: list, base: Path | None = None) -> list[Path]:
    if not isinstance(refs, list):
        raise InvalidPathError("Expected a list of file paths.")
    return [resolve_ref(r, base) for r in refs]


def allowed(filename: str, extensions: list[str] | tuple[str, ...]) -> bool:
    return Path(filename).suffix.lower().lstrip(".") in extensions


def save_uploads(kind: str, uploads, extensions) -> tuple[list[dict], list[str]]:
    """Saves uploaded files (werkzeug FileStorage objects) into the staging folder of `kind`."""
    target = staging_dir(kind)
    target.mkdir(parents=True, exist_ok=True)
    saved, rejected = [], []
    for upload in uploads:
        name = Path(upload.filename or "").name
        # secure_filename() drops non-ASCII characters (e.g. Chinese book titles): only fall back to it when needed.
        if not name or name.startswith(".") or "/" in name or "\\" in name:
            name = secure_filename(upload.filename or "")
        if not name or not allowed(name, extensions):
            rejected.append(upload.filename or "?")
            continue
        path = target / name
        upload.save(path)
        saved.append(describe(path))
    return saved, rejected


def discard(ref: str) -> bool:
    """Deletes a staged upload. Files living in sources/audiobook or sources/ebook are only dropped from the page's
    list, never deleted."""
    path = resolve_ref(ref, must_exist=False)
    if path.is_relative_to(paths.staging.resolve()) and path.is_file():
        path.unlink()
        return True
    return False


def preload() -> dict:
    """The files already in sources/, shown when the page opens."""
    found = source_files.sources()
    return {kind: [describe(f) for f in files] for kind, files in found.items()}
