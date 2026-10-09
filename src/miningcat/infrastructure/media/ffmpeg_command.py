import os
import shutil
from pathlib import Path
from typing import Self


class FfmpegCommand:
    """Builds an ffmpeg command line, in ffmpeg's order: the inputs, then what goes to the output.

        FfmpegCommand().input(video).input(subtitles).map("0:v").codec("v", "copy").overwrite().build(output)
    """

    def __init__(self):
        self._inputs: list[str] = []
        self._options: list[str] = []

    def input(self, path: Path | str, *options: str) -> Self:
        """An input file, after its own options (-loop 1, -ss 10...)."""
        self._inputs += [*options, "-i", str(path)]
        return self

    def map(self, *specs: str) -> Self:
        for spec in specs:
            self._options += ["-map", spec]
        return self

    def codec(self, stream: str, codec: str) -> Self:
        self._options += [f"-c:{stream}", codec]
        return self

    def metadata(self, stream: str, key: str, value: str) -> Self:
        """Metadata of an output stream (s:s:0 is the first subtitle stream)."""
        self._options += [f"-metadata:{stream}", f"{key}={value}"]
        return self

    def option(self, *args: str) -> Self:
        self._options += list(args)
        return self

    def overwrite(self) -> Self:
        return self.option("-y")

    def build(self, output: Path | str) -> list[str]:
        return ["ffmpeg", *self._inputs, *self._options, str(output)]


def link_or_copy(source: Path, link: Path) -> Path:
    """A symlink to `source` at `link` (or a copy, where symlinks aren't available): ffmpeg chokes on some paths."""
    if link.exists() or link.is_symlink():
        link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(source.absolute(), link.absolute())
    except (OSError, NotImplementedError):
        shutil.copy(source, link)
    return link
