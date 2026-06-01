# align.py — Forced alignment of chapter text to audio.

import re
import time
from dataclasses import dataclass
from pathlib import Path

import stable_whisper
from tqdm import tqdm

from config import DIR_CHAPTERS_AUDIO, DIR_CHAPTERS_TEXT, DIR_SRT
from language import Language


def get_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

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


# save segments to SRT file
def save_srt(segs: list[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(segs, 1):
        s.index = i
    path.write_text("\n".join(s.to_srt() for s in segs), encoding="utf-8")

# Move leading closing punctuation to the end of the previous segment.
def fix_leading_punct(segs: list[Segment], lang: Language = Language.MANDARIN_TW) -> list[Segment]:
    closing_punct = lang.value.closing_punct
    result: list[Segment] = []
    for seg in segs:
        text = seg.text
        i = 0
        while i < len(text) and text[i] in closing_punct:
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
def prepare_text(raw: str, lang: Language = Language.MANDARIN_TW) -> str:
    text = re.sub(lang.value.vocab_annotation_pattern, '', raw)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()

def _extract_segments(result, lang: Language) -> list[Segment]:
    raw_segs = result.segments if hasattr(result, "segments") else result.get("segments", [])
    segs = []
    for seg in raw_segs:
        start = seg.start if hasattr(seg, "start") else seg["start"]
        end   = seg.end   if hasattr(seg, "end")   else seg["end"]
        text  = (seg.text if hasattr(seg, "text")  else seg["text"]).strip()
        if text:
            segs.append(Segment(0, start, end, text))
    return fix_leading_punct(segs, lang)

# Align a single chapter's audio and text, returning a list of segments with timestamps.
def align_chapter(
    model,
    audio_file: Path,
    text_file: Path,
    lang: Language = Language.MANDARIN_TW,
) -> tuple[list[Segment], int]:
    # Load and prepare text, then run alignment.
    chapter_text = prepare_text(text_file.read_text(encoding="utf-8").strip(), lang)
    result = model.align(
        str(audio_file),
        chapter_text,
        language=lang.value.whisper_code,
        verbose=False,
    )
    segs = _extract_segments(result, lang)
    return segs, len(chapter_text)

def transcribe_chapter(
    model,
    audio_file: Path,
    lang: Language = Language.MANDARIN_TW,
) -> list[Segment]:
    result = model.transcribe(
        str(audio_file),
        language=lang.value.whisper_code,
        verbose=False,
    )
    return _extract_segments(result, lang)


def run_transcribe(
    model_name: str = "tiny",
    language: Language = Language.MANDARIN_TW,
    from_ch: int | None = None,
    only_ch: int | None = None,
) -> None:
    import sys

    if only_ch is not None:
        from_ch = only_ch

    if not DIR_CHAPTERS_AUDIO.exists():
        print(f"Error: {DIR_CHAPTERS_AUDIO} not found — Run 'audio' first")
        sys.exit(1)

    DIR_SRT.mkdir(parents=True, exist_ok=True)

    audio_files = sorted(DIR_CHAPTERS_AUDIO.glob("*.mp3"))
    print(f"Audio chapters: {len(audio_files)}")

    start_idx = (from_ch - 1) if from_ch else 0
    files = audio_files[start_idx:]
    print()

    print(f"Loading stable-whisper model '{model_name}'...")
    model = stable_whisper.load_model(model_name, device=get_device())
    print()

    for i, audio_file in enumerate(
        tqdm(files, desc="Chapters"), start=start_idx
    ):
        ch_num = i + 1
        srt_out = DIR_SRT / (audio_file.stem + ".srt")

        if srt_out.exists() and from_ch is None:
            tqdm.write(f"  Ch.{ch_num:03d} skip")
            continue

        t0 = time.time()
        segs = transcribe_chapter(model, audio_file, lang=language)
        save_srt(segs, srt_out)
        elapsed = time.time() - t0

        tqdm.write(f"  Ch.{ch_num:03d}  {len(segs)} seg  {elapsed:.0f}s")

        if only_ch is not None:
            break

    print("\nDone.")


# Run alignment for all chapters, with options to start from a specific chapter or only process one chapter.
def run(
    model_name: str = "tiny",
    language: Language = Language.MANDARIN_TW,
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
    model = stable_whisper.load_model(model_name, device=get_device())
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
        segs, text_len = align_chapter(model, audio_file, text_file, lang=language)
        save_srt(segs, srt_out)
        elapsed = time.time() - t0

        tqdm.write(
            f"  Ch.{ch_num:03d}  {len(segs)} seg  {elapsed:.0f}s  "
            f"ebook={text_len:,}c"
        )

        if only_ch is not None:
            break

    print("\nDone.")
