# align.py — Forced alignment of chapter text to audio.

import re
import time
from dataclasses import dataclass
from pathlib import Path

import stable_whisper
from tqdm import tqdm

from config import DIR_CHAPTERS_AUDIO, DIR_CHAPTERS_TEXT, DIR_SRT


@dataclass
class Segment:
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


# Closing punctuation that should be moved to the end of the previous segment if it appears at the start of a segment.
_CLOSING_PUNCT = set('。？！」')


# save segments to SRT file
def save_srt(segs: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(segs, 1):
        s.index = i
    path.write_text("\n".join(s.to_srt() for s in segs), encoding="utf-8")

# Move leading closing punctuation to the end of the previous segment.
def fix_leading_punct(segs: list[Segment]) -> list[Segment]:
    # Move leading closing punctuation to the end of the previous segment.
    result: list[Segment] = []
    for seg in segs:
        text = seg.text
        i = 0
        while i < len(text) and text[i] in _CLOSING_PUNCT:
            i += 1
        leading = text[:i]
        remainder = text[i:].lstrip()

        if leading and result:
            prev = result[-1]
            result[-1] = Segment(prev.index, prev.start, prev.end, prev.text + leading)
            if remainder:
                result.append(Segment(seg.index, seg.start, seg.end, remainder))
        else:
            result.append(seg)

    return result


# This is the main alignment function, which takes an audio file and a text file, and returns a list of aligned segments.
def prepare_text(raw: str) -> str:
    # Strip [N] vocabulary annotations and blank lines left behind.
    text = re.sub(r'\[\d+\]', '', raw)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()

# Align a single chapter's audio and text, returning a list of segments with timestamps.
def align_chapter(
    model,
    audio_file: Path,
    text_file: Path,
    language: str = "zh",
) -> list[Segment]:
    # Load and prepare text, then run alignment.
    chapter_text = prepare_text(text_file.read_text(encoding="utf-8").strip())
    result = model.align(
        str(audio_file),
        chapter_text,
        language=language,
        verbose=False,
    )
    # The result may have segments in result.segments or result["segments"] depending on the model version, so we check both.
    raw_segs = result.segments if hasattr(result, "segments") else result.get("segments", [])
    segs = []
    # Each segment has start, end, and text. We create Segment objects and then fix leading punctuation.
    for seg in raw_segs:
        start = seg.start if hasattr(seg, "start") else seg["start"]
        end   = seg.end   if hasattr(seg, "end")   else seg["end"]
        text  = (seg.text if hasattr(seg, "text")  else seg["text"]).strip()
        if text:
            segs.append(Segment(0, start, end, text))
    return fix_leading_punct(segs)

# Run alignment for all chapters, with options to start from a specific chapter or only process one chapter.
def run(
    model_name: str = "tiny",
    language: str = "zh",
    from_ch: int | None = None,
    only_ch: int | None = None,
) -> None:
    import sys

    # If only_ch is specified, we set from_ch to the same value to process only that chapter.
    if only_ch is not None:
        from_ch = only_ch

    for p, msg in [
        (DIR_CHAPTERS_AUDIO, "Run 'audio' first"),
        (DIR_CHAPTERS_TEXT,  "Run 'epub' first"),
    ]:
        if not p.exists():
            print(f"Error: {p} not found — {msg}")
            sys.exit(1)

    DIR_SRT.mkdir(parents=True, exist_ok=True)

    audio_files = sorted(DIR_CHAPTERS_AUDIO.glob("*.mp3"))
    text_files  = sorted(DIR_CHAPTERS_TEXT.glob("chapter_*.txt"))

    print(f"Audio chapters: {len(audio_files)}")
    print(f"Text chapters:  {len(text_files)}")

# If the counts don't match, we warn but continue with the minimum of the two.
    if len(audio_files) != len(text_files):
        print(f"Warning: {len(audio_files)} audio vs {len(text_files)} text — "
              f"processing min({len(audio_files)}, {len(text_files)}).")

    start_idx = (from_ch - 1) if from_ch else 0
    pairs = list(zip(audio_files, text_files))[start_idx:]
    print()

    # Load stable-whisper
    print(f"Loading stable-whisper model '{model_name}'...")
    model = stable_whisper.load_model(model_name, device="cpu")
    print()

    # Process each chapter, skipping already existing SRT files unless from_ch is specified (which indicates a retry).
    for i, (audio_file, text_file) in enumerate(
        # We use tqdm to show progress
        tqdm(pairs, desc="Chapters"), start=start_idx
    ):
        ch_num = i + 1
        srt_out = DIR_SRT / (audio_file.stem + ".srt")

        if srt_out.exists() and from_ch is None:
            tqdm.write(f"  Ch.{ch_num:03d} skip")
            continue

        t0 = time.time()
        segs = align_chapter(model, audio_file, text_file, language=language)
        save_srt(segs, srt_out)
        elapsed = time.time() - t0

        text_len = len(prepare_text(text_file.read_text(encoding="utf-8").strip()))
        tqdm.write(
            f"  Ch.{ch_num:03d}  {len(segs)} seg  {elapsed:.0f}s  "
            f"ebook={text_len:,}c"
        )

        if only_ch is not None:
            break

    print("\nDone.")
