from pathlib import Path

AUDIO_EXTENSIONS = ("mp3", "m4a", "aac", "ogg", "wav", "flac", "opus", "m4b")
# Format of the chapters cut from an audiobook, and of the audio extracted from videos.
AUDIO_FORMAT = "mp3"
AUDIO_BITRATE = "192k"


def glob_audio_files(directory: Path) -> list[Path]:
    """The audio files of a folder, sorted by name."""
    if not directory.exists():
        return []
    return sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower().lstrip(".") in AUDIO_EXTENSIONS
    )
