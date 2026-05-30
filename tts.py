import asyncio
from pathlib import Path

import edge_tts
from tqdm import tqdm

from config import DIR_CHAPTERS_TEXT, DIR_CHAPTERS_AUDIO, DIR_SRT
from align import Segment, save_srt

_TICKS_PER_SECOND = 10_000_000

# Synthesize the given text to the given audio path, and save the sentence boundary events as an SRT file.
async def _synthesize(text: str, voice: str, audio_path: Path, srt_path: Path) -> int:
    communicate = edge_tts.Communicate(text, voice)

    audio_buf = bytearray()
    raw_events: list[dict] = []

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buf.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            raw_events.append(chunk)

    audio_path.write_bytes(bytes(audio_buf))

    # Build segments, clipping each end to the next sentence's start to avoid overlaps.
    segments: list[Segment] = []
    for i, ev in enumerate(raw_events):
        start = ev["offset"] / _TICKS_PER_SECOND
        end   = (ev["offset"] + ev["duration"]) / _TICKS_PER_SECOND
        if i + 1 < len(raw_events):
            next_start = raw_events[i + 1]["offset"] / _TICKS_PER_SECOND
            end = min(end, next_start - 0.05)
        sentence = ev.get("text", "").strip()
        if sentence:
            segments.append(Segment(0, start, end, sentence))

    save_srt(segments, srt_path)
    return len(segments)


def run(voice: str) -> None:
    import sys

    if not DIR_CHAPTERS_TEXT.exists():
        print(f"Error: {DIR_CHAPTERS_TEXT} not found - Run 'epub' first")
        sys.exit(1)

    text_files = sorted(DIR_CHAPTERS_TEXT.glob("chapter_*.txt"))
    if not text_files:
        print(f"Error: no chapter_*.txt files found in {DIR_CHAPTERS_TEXT}")
        sys.exit(1)

    DIR_CHAPTERS_AUDIO.mkdir(parents=True, exist_ok=True)
    DIR_SRT.mkdir(parents=True, exist_ok=True)

    print(f"Text chapters : {len(text_files)}")
    print(f"Voice         : {voice}")
    print()

# Synthesize each chapter, skipping if the output files already exist.
    for text_file in tqdm(text_files, desc="Chapters"):
        audio_path = DIR_CHAPTERS_AUDIO / (text_file.stem + ".mp3")
        srt_path   = DIR_SRT / (text_file.stem + ".srt")

        if audio_path.exists() and srt_path.exists():
            tqdm.write(f"  {text_file.stem} skip")
            continue

        text = text_file.read_text(encoding="utf-8").strip()
        n_segs = asyncio.run(_synthesize(text, voice, audio_path, srt_path))
        tqdm.write(f"  {text_file.stem}  {n_segs} seg")

    print("\nDone.")
