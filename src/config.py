# config.py - Global paths and configuration.

from pathlib import Path

#  Project root 
ROOT = Path(__file__).parent.parent

#  Sources 
DIR_EBOOK     = ROOT / "sources" / "ebook"
DIR_AUDIOBOOK = ROOT / "sources" / "audiobook"

#  Outputs 
DIR_CHAPTERS_AUDIO = ROOT / "output" / "chapters_audio"
DIR_CHAPTERS_TEXT  = ROOT / "output" / "chapters_text"
DIR_SRT            = ROOT / "output" / "srt"
DIR_FINAL          = ROOT / "output" / "final"
DIR_TEMP = ROOT / "output" / "temp"

#  Intermediate audio format
AUDIO_FORMAT  = "mp3"
AUDIO_BITRATE = "192k"

#  Font candidates for video overlay (ordered by Unicode/CJK coverage)
FONT_CANDIDATES = [
    # macOS - CJK support
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    # Linux - CJK support
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    # Windows - CJK support
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    # Latin fallbacks
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

AUDIO_EXTENSIONS = ("mp3", "m4a", "aac", "ogg", "wav", "flac", "opus", "m4b")


def detect_audio_mode() -> tuple[str, list[Path]]:
    # Detect which audio input mode to use:
    # - 'multi_audio'  : multiple files, each treated as one chapter
    # - 'single_m4b'   : single .m4b file to be split by chapter markers
    # - 'single_audio' : single file (treated as one chapter)
    all_files = glob_audio_files(DIR_AUDIOBOOK)
    if not all_files:
        raise FileNotFoundError(f"No audio file found in {DIR_AUDIOBOOK}")
    if len(all_files) > 1:
        return "multi_audio", all_files
    if all_files[0].suffix.lower() == ".m4b":
        return "single_m4b", all_files
    return "single_audio", all_files


def glob_audio_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower().lstrip(".") in AUDIO_EXTENSIONS
    )