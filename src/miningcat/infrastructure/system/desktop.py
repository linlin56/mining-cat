import os
import platform
import subprocess
from pathlib import Path


def open_folder(path: Path) -> None:
    """Opens a folder (created if needed) in the system's file manager."""
    path.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Windows":
        os.startfile(str(path))
    elif platform.system() == "Darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])
