import os
import platform
import re
import subprocess
from pathlib import Path


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        os.startfile(str(path))
    elif platform.system() == "Darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


_SRT_TIMESTAMP_RE = re.compile(r'^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}$')


# Strip index numbers and timestamp lines from an SRT file, keeping only the dialogue text.
def srt_to_text(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit() or _SRT_TIMESTAMP_RE.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)
