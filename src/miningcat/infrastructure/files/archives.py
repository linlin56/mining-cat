"""Archives of comics, unpacked without trusting their paths."""
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable


class ArchiveError(ValueError):
    pass


def unzip(archive: Path, target: Path, keep: Callable[[str], bool]) -> None:
    """Extracts the files of a zip archive that `keep` accepts."""
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir() or not keep(info.filename):
                    continue
                # the archive's paths are never trusted as they are: no absolute paths, no "..", no drive letters
                parts = [p for p in PurePosixPath(info.filename.replace("\\", "/")).parts if p not in ("", "/", "..") and ":" not in p]
                if not parts:
                    continue
                dest = target.joinpath(*parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile:
        raise ArchiveError("This archive is damaged, or isn't a ZIP archive.")


def untar(archive: Path, target: Path) -> None:
    """Extracts a RAR, 7z or tar archive: the bsdtar of macOS (libarchive) reads them; elsewhere it may need installing."""
    tool = shutil.which("bsdtar") or shutil.which("tar")
    if tool is None:
        raise ArchiveError("Unpacking this archive needs bsdtar (libarchive). Convert it to .cbz, or install bsdtar.")
    result = subprocess.run([tool, "-xf", str(archive), "-C", str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise ArchiveError(f"This archive couldn't be unpacked{': ' + detail[-1] if detail else ''}. Try converting it to .cbz.")
    # the extracted names come from the archive: drop anything that escaped the folder (absolute paths, links)
    root = target.resolve()
    for path in list(target.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            path.unlink(missing_ok=True)
