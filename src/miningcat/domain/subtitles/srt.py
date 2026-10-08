"""Reading SRT subtitles."""
import re
from dataclasses import dataclass

_TIMESTAMP = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})")


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_srt(text: str) -> list[Cue]:
    """The cues of an SRT file (their formatting tags removed)."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            m = _TIMESTAMP.search(line)
            if m:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(v) for v in m.groups())
                cue_text = " ".join(l.strip() for l in lines[i + 1:] if l.strip())
                cue_text = re.sub(r"<[^>]+>", "", cue_text)
                cues.append(Cue(h1 * 3600 + m1 * 60 + s1 + ms1 / 1000, h2 * 3600 + m2 * 60 + s2 + ms2 / 1000, cue_text))
                break
    return cues



_SRT_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}$")


def srt_text(srt: str) -> str:
    """The dialogue of an SRT file, without its numbers and timestamps: one line per subtitle line."""
    lines = []
    for line in srt.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit() or _SRT_TIMESTAMP_LINE.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)
