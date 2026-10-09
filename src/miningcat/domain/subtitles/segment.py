from dataclasses import dataclass


@dataclass
class Segment:
    """A subtitle: its number, its start and end in seconds, and its text."""

    index: int
    start: float
    end: float
    text: str

    # Format time in SRT format: "HH:MM:SS,mmm"
    def _fmt(self, t: float) -> str:
        h, rem = divmod(t, 3600)
        m, s = divmod(rem, 60)
        ms = (s % 1) * 1000
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(ms):03d}"

    def to_srt(self) -> str:
        return f"{self.index}\n{self._fmt(self.start)} --> {self._fmt(self.end)}\n{self.text}\n"



def format_srt(segments: list[Segment]) -> str:
    """The SRT file of some segments, numbered from 1."""
    for i, segment in enumerate(segments, 1):
        segment.index = i
    return "\n".join(s.to_srt() for s in segments)
