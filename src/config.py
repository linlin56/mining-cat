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


def detect_audio_mode() -> tuple[str, list[Path]]:
    # Detect which audio input mode to use:
    # - 'multi_mp3'  : multiple .mp3 files, each treated as one chapter
    # - 'single_m4b' : single .m4b file to be split by chapter markers
    # - 'single_mp3' : single .mp3 file (chapter splitting not yet supported)
    mp3_files = sorted(DIR_AUDIOBOOK.glob("*.mp3"))
    if len(mp3_files) > 1:
        return "multi_mp3", mp3_files
    m4b_files = sorted(DIR_AUDIOBOOK.glob("*.m4b"))
    if m4b_files:
        return "single_m4b", m4b_files[:1]
    if mp3_files:
        return "single_mp3", mp3_files
    raise FileNotFoundError(f"No audio file found in {DIR_AUDIOBOOK}")


