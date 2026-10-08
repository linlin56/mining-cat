import sys
from pathlib import Path


# gui_components/ -> src/ -> project root
ROOT    = Path(__file__).parent.parent.parent
SRC_DIR = Path(__file__).parent.parent

DIR_AUDIOBOOK = ROOT / "sources" / "audiobook"
DIR_EBOOK     = ROOT / "sources" / "ebook"
DIR_FINAL     = ROOT / "output" / "final"

import platform
_VENV_PYTHON = (
    ROOT / ".venv" / "Scripts" / "python.exe"
    if platform.system() == "Windows"
    else ROOT / ".venv" / "bin" / "python3"
)
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

STEPS = [
    ("Step 1/4 - Audio preparation",  10,  "audio",     []),
    ("Step 2/4 - EPUB extraction",    25,  "epub",      []),
    ("Step 3/4 - Alignment",          40,  "align",     []),
    ("Step 4/4 - MP4 export",         80,  "export",    ["--all"]),
]

STEPS_WHISPER = [
    ("Step 1/3 - Audio preparation",  10,  "audio",      []),
    ("Step 2/3 - Transcription",      40,  "transcribe", []),
    ("Step 3/3 - MP4 export",         80,  "export",     ["--all"]),
]

STEPS_TTS = [
    ("Step 1/3 - EPUB extraction",   10,  "epub",   []),
    ("Step 2/3 - Audio + subtitles", 40,  "tts",    []),
    ("Step 3/3 - MP4 export",        80,  "export", ["--all"]),
]

_CONVERT_OPTIONS_FOR_SCRIPT: dict[str, list[tuple[str, str | None]]] = {
    "s": [
        ("No conversion", None),
        ("Traditional - Taiwan", "tw"),
        ("Traditional - Chinese", "t"),
    ],
    "tw": [
        ("No conversion", None),
        ("Simplified - China", "s"),
    ],
    "hk": [
        ("No conversion", None),
        ("Simplified - China", "s"),
    ],
}
CONVERT_BY_LABEL: dict[str, str | None] = {
    label: code
    for options in _CONVERT_OPTIONS_FOR_SCRIPT.values()
    for label, code in options
}

GITHUB_URL = "https://github.com/linlin56/mining-cat"

# Video screen (shared by the Tkinter and web GUIs). To add a platform, also register its handler in video_handlers/.
TARGET_WEBSITES = ["Instagram", "YouTube", "Bilibili"]
INPUT_MODES = ["From web", "Local file"]

# Example URL shown as greyed-out placeholder text in the URL entry, per selected website.
URL_HINT_BY_WEBSITE = {
    "Instagram": "https://www.instagram.com/reel/...",
    "YouTube": "https://www.youtube.com/watch?v=... or https://youtu.be/...",
    "Bilibili": "https://www.bilibili.com/video/BV...",
}
