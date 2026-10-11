"""Generate audio mode: each chapter of the book read by OmniVoice, an edge-tts voice or Taigi's MMS voice, with its
subtitles."""
import asyncio
from pathlib import Path

from tqdm import tqdm

from miningcat.application.anki.config import get_config
from miningcat.application.converter.errors import ConverterError
from miningcat.config.paths import paths
from miningcat.domain.languages import Language
from miningcat.domain.subtitles.punctuation import restore_opening_punct
from miningcat.domain.subtitles.segment import Segment
from miningcat.domain.text.sentences import split_sentences
from miningcat.infrastructure.files.srt_files import save_srt
from miningcat.infrastructure.speech import mms_tts, omnivoice_tts
from miningcat.infrastructure.speech.edge_tts import TICKS_PER_SECOND, EdgeTts

# Gap left between a subtitle and the next one.
_SUBTITLE_GAP_S = 0.05


def sentence_segments(events: list[dict]) -> list[Segment]:
    """Subtitles from edge-tts sentence boundaries, each one ending before the next one starts."""
    segments: list[Segment] = []
    for i, event in enumerate(events):
        start = event["offset"] / TICKS_PER_SECOND
        end = (event["offset"] + event["duration"]) / TICKS_PER_SECOND
        if i + 1 < len(events):
            end = min(end, events[i + 1]["offset"] / TICKS_PER_SECOND - _SUBTITLE_GAP_S)
        sentence = event.get("text", "").strip()
        if sentence:
            segments.append(Segment(0, start, end, sentence))
    return segments


async def _synthesize(text: str, voice: str, audio_path: Path, srt_path: Path,
                      lang: Language = Language.MANDARIN_TW) -> int:
    """Writes the audio of a text and its subtitles. Returns the number of subtitles."""
    audio, events = await EdgeTts.stream(text, voice)
    audio_path.write_bytes(audio)
    segments = restore_opening_punct(sentence_segments(events), text, lang)
    save_srt(segments, srt_path)
    return len(segments)


# A local voice (Taigi's MMS voice) reads the chapter sentence by sentence: the subtitles are its sentences.
def _synthesize_local(text: str, voice: str, audio_path: Path, srt_path: Path) -> int:
    timed = mms_tts.synthesize_chapter(split_sentences(text), voice, audio_path)
    return _save_timed(timed, srt_path)


# OmniVoice reads the chapter sentence by sentence too, with the voice of the language.
def _synthesize_omnivoice(text: str, lang: Language, audio_path: Path, srt_path: Path, steps: int) -> int:
    timed = omnivoice_tts.synthesize_chapter(split_sentences(text), lang.profile.key, audio_path, steps)
    return _save_timed(timed, srt_path)


def _save_timed(timed: list[tuple[float, float, str]], srt_path: Path) -> int:
    save_srt([Segment(0, start, end, sentence) for start, end, sentence in timed], srt_path)
    return len(timed)


def _synthesize_chapter(text: str, voice: str, lang: Language, audio_path: Path, srt_path: Path, config: dict) -> int:
    """Reads a chapter with the voice: MMS's, OmniVoice's or Edge's (OmniVoice taking over when Edge fails). Returns
    the number of subtitles."""
    if mms_tts.is_local(voice):
        return _synthesize_local(text, voice, audio_path, srt_path)
    steps = config["tts_steps"]
    if omnivoice_tts.is_voice(voice):
        return _synthesize_omnivoice(text, lang, audio_path, srt_path, steps)
    try:
        return asyncio.run(_synthesize(text, voice, audio_path, srt_path, lang))
    except Exception as exc:  # network errors, Edge refusing the request...
        if not (omnivoice_tts.installed() and omnivoice_tts.supports(lang.profile.key)):
            raise
        tqdm.write(f"  Edge failed ({exc}): OmniVoice reads the chapter")
        return _synthesize_omnivoice(text, lang, audio_path, srt_path, steps)


def run(voice: str, lang: Language = Language.MANDARIN_TW) -> None:
    """Reads each chapter of output/chapters_text into output/chapters_audio and output/srt (chapters already
    done are skipped)."""
    if not paths.chapters_text.exists():
        raise ConverterError(f"{paths.chapters_text} not found - Run 'epub' first")
    text_files = sorted(paths.chapters_text.glob("chapter_*.txt"))
    if not text_files:
        raise ConverterError(f"no chapter_*.txt files found in {paths.chapters_text}")

    paths.chapters_audio.mkdir(parents=True, exist_ok=True)
    paths.srt.mkdir(parents=True, exist_ok=True)
    config = get_config()
    print(f"Text chapters : {len(text_files)}")
    print(f"Voice         : {voice}")
    print()

    for text_file in tqdm(text_files, desc="Chapters"):
        audio_path = paths.chapters_audio / (text_file.stem + ".mp3")
        srt_path = paths.srt / (text_file.stem + ".srt")
        if audio_path.exists() and srt_path.exists():
            tqdm.write(f"  {text_file.stem} skip")
            continue
        text = text_file.read_text(encoding="utf-8").strip()
        n_segs = _synthesize_chapter(text, voice, lang, audio_path, srt_path, config)
        tqdm.write(f"  {text_file.stem}  {n_segs} seg")

    print("\nDone.")
