from enum import Enum
from pathlib import Path


class AudioSourceMode(Enum):
    """How the audio files of an audiobook become its chapters."""

    MULTI_AUDIO = "multi_audio"      # several files: one chapter each
    SINGLE_M4B = "single_m4b"        # one .m4b file, split by its chapter markers
    SINGLE_AUDIO = "single_audio"    # one file: one chapter

    @classmethod
    def of(cls, files: list[Path]) -> "AudioSourceMode":
        if len(files) > 1:
            return cls.MULTI_AUDIO
        if files[0].suffix.lower() == ".m4b":
            return cls.SINGLE_M4B
        return cls.SINGLE_AUDIO
