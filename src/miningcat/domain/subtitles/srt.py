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


# Formatting around a subtitle line, kept as it is when the line is translated: SRT tags (<i>, <font ...>), ASS tags
# ({\an8}), the dash of a dialogue line.
_LINE_AFFIXES = re.compile(r"^((?:\s|-|<[^>]+>|\{[^}]*\})*)(.*?)((?:\s|<[^>]+>|\{[^}]*\})*)$", re.S)
_INNER_TAGS = re.compile(r"<[^>]+>|\{[^}]*\}")


def _text_lines(text: str) -> list[list[str]]:
    """The blocks of an SRT file, as lines; a block's text lines are the ones after its timestamp line."""
    return [block.splitlines() for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())]


def _split_line(line: str) -> tuple[str, str, str]:
    """(formatting before, text, formatting after) of a subtitle line. A tag closed inside the line (<b>a</b> b) can't
    be put back in a translation: then the line's tags are left out."""
    before, inner, after = _LINE_AFFIXES.match(line).groups()
    if _INNER_TAGS.search(inner):
        before, after = re.sub(r"<[^>]+>", "", before), re.sub(r"<[^>]+>", "", after)
    return before, _INNER_TAGS.sub("", inner).strip(), after


def _timestamp_index(lines: list[str]) -> int | None:
    return next((i for i, line in enumerate(lines) if _TIMESTAMP.search(line)), None)


def srt_lines(text: str) -> list[str]:
    """The text of every subtitle line of an SRT file, without its formatting, each once, in order."""
    found = []
    for lines in _text_lines(text):
        i = _timestamp_index(lines)
        if i is not None:
            found += [inner for _, inner, _ in map(_split_line, lines[i + 1:]) if inner]
    return list(dict.fromkeys(found))


def replace_srt_lines(text: str, replacements: dict[str, str]) -> str:
    """The SRT file with its subtitle lines replaced (by their text, see srt_lines()): numbers, timestamps, line
    breaks and formatting stay the same."""
    blocks = []
    for lines in _text_lines(text):
        i = _timestamp_index(lines)
        if i is not None:
            for j in range(i + 1, len(lines)):
                before, inner, after = _split_line(lines[j])
                if inner in replacements:
                    lines[j] = f"{before}{replacements[inner]}{after}"
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
