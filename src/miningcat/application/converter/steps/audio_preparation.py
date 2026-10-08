"""Step 1 of an audiobook: its audio files become chapters in output/chapters_audio."""
import json
import shutil
from pathlib import Path

from tqdm import tqdm

from miningcat.application.converter.errors import ConverterError
from miningcat.config.paths import paths
from miningcat.domain.audiobook.chapter import Chapter, format_timestamp
from miningcat.domain.audiobook.source_mode import AudioSourceMode
from miningcat.infrastructure.media.audio_files import glob_audio_files
from miningcat.infrastructure.media.m4b import extract_chapter, probe_chapters


def detect_audio_mode() -> tuple[AudioSourceMode, list[Path]]:
    """How the files of sources/audiobook are split into chapters."""
    files = glob_audio_files(paths.audiobook)
    if not files:
        raise ConverterError(f"No audio file found in {paths.audiobook}")
    return AudioSourceMode.of(files), files


def print_chapters(chapters: list[Chapter], m4b_path: Path) -> None:
    total = sum(c.duration for c in chapters)
    print(f"\nFile     : {m4b_path.name}")
    print(f"Chapters : {len(chapters)}")
    print(f"Total    : {format_timestamp(total)}\n")
    print(f"  {'#':>4}  {'Start':>10}  {'End':>10}  {'Duration':>10}  Title")
    print("  " + "-" * 70)
    for c in chapters:
        print(f"  {c.index:>4}  {c.start_str:>10}  {c.end_str:>10}  {format_timestamp(c.duration):>10}  {c.title}")
    print()


def save_chapters_json(chapters: list[Chapter], output_dir: Path) -> Path:
    data = [
        {"index": c.index, "title": c.title, "start_time": c.start_time, "end_time": c.end_time, "slug": c.slug}
        for c in chapters
    ]
    out = output_dir / "chapters.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Chapters saved: {out}")
    return out


def extract_all_chapters(m4b_path: Path, chapters: list[Chapter], output_dir: Path) -> list[Path]:
    """Cuts the chapters of an .m4b file into separate audio files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {len(chapters)} chapters to {output_dir}/\n")
    return [extract_chapter(m4b_path, chapter, output_dir) for chapter in tqdm(chapters, unit="chapter")]


def copy_audio_chapters(audio_files: list[Path], output_dir: Path) -> list[Path]:
    """Several audio files are one chapter each: they're copied as they are."""
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    print(f"{len(audio_files)} audio files found - multi-chapter mode\n")
    for src in audio_files:
        dst = output_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"  Copied: {src.name}")
        else:
            print(f"  Already present: {src.name}")
        copied.append(dst)
    return copied


def _copy_files(mode: AudioSourceMode, audio_files: list[Path], dry_run: bool) -> None:
    if mode is AudioSourceMode.MULTI_AUDIO:
        print(f"Mode: multi-audio ({len(audio_files)} files = {len(audio_files)} chapters)")
    else:
        print("Mode: single-audio (treated as one chapter)")
    for f in audio_files:
        print(f"  {f.name}")
    print()
    if dry_run:
        print("Dry-run: no files copied.")
        return
    copied = copy_audio_chapters(audio_files, paths.chapters_audio)
    print(f"\n{len(copied)} {'chapters' if mode is AudioSourceMode.MULTI_AUDIO else 'chapter'} ready in {paths.chapters_audio}/")


def _split_m4b(m4b_path: Path, dry_run: bool) -> None:
    print(f"Analysing {m4b_path.name} ...")
    chapters = probe_chapters(m4b_path)
    if not chapters:
        raise ConverterError("No chapters found in the .m4b file.")
    print_chapters(chapters, m4b_path)
    if dry_run:
        print("Dry-run: no files extracted.")
        return
    # The chapters' metadata is kept for later steps.
    paths.temp.mkdir(parents=True, exist_ok=True)
    save_chapters_json(chapters, paths.temp)
    extracted = extract_all_chapters(m4b_path, chapters, paths.chapters_audio)
    print(f"\n{len(extracted)} chapters extracted to {paths.chapters_audio}/")


def run(dry_run: bool = False) -> None:
    """Copies the audio files of sources/audiobook, or cuts its .m4b file by chapter, into output/chapters_audio."""
    mode, audio_files = detect_audio_mode()
    if mode is AudioSourceMode.SINGLE_M4B:
        _split_m4b(audio_files[0], dry_run)
    else:
        _copy_files(mode, audio_files, dry_run)
