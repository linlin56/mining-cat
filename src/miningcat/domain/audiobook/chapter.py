from dataclasses import dataclass


@dataclass
class Chapter:
    """A chapter of an audiobook file (from its chapter markers)."""

    index: int
    title: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def start_str(self) -> str:
        return format_timestamp(self.start_time)

    @property
    def end_str(self) -> str:
        return format_timestamp(self.end_time)

    # A slug for the chapter, used in filenames. It includes the index and a sanitized version of the title.
    @property
    def slug(self) -> str:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.title)
        safe = safe.strip().replace(" ", "_")
        return f"{self.index:03d}_{safe}"


def format_timestamp(seconds: float) -> str:
    """3661.5 -> "01:01:01.500"."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
