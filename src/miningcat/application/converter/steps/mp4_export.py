"""Step 4 of an audiobook: one MP4 per chapter, its audio over the book's cover, with its subtitles."""
import json
from pathlib import Path

from tqdm import tqdm

from miningcat.application.converter.ebook_source import epub_cover, epub_title
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.steps.ebook_extraction import MANIFEST_NAME
from miningcat.config.paths import paths
from miningcat.infrastructure.media.audio_files import glob_audio_files
from miningcat.infrastructure.media.still_video import export_still_video
from miningcat.infrastructure.media.title_card import TitleCardRenderer


def video_frame(width: int = 1920, height: int = 1080, book_title: str | None = None,
                chapter_title: str | None = None, chapter_stem: str | None = None) -> Path:
    """The still image of a chapter's video (made once, then kept in output/temp)."""
    output_path = paths.temp / f"video_frame_{chapter_stem or 'default'}.png"
    if output_path.exists():
        return output_path
    frame = TitleCardRenderer(width, height).render(epub_cover(), book_title, chapter_title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(output_path)
    return output_path


def chapter_titles() -> dict[int, str]:
    """{chapter number: title}, from the manifest of the ebook extraction."""
    manifest_path = paths.temp / MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {e["index"]: e["title"] for e in entries if "index" in e and "title" in e}
    except Exception:
        return {}


def chapter_audio_files() -> list[Path]:
    files = glob_audio_files(paths.chapters_audio)
    if not files:
        raise FileNotFoundError(f"No audio file found in {paths.chapters_audio}")
    return files


def export_chapter(audio_file: Path, frame: Path, output_file: Path, preset: str = "ultrafast",
                   subtitle_lang: str = "zho") -> bool:
    srt_file = paths.srt / (audio_file.stem + ".srt")
    if not srt_file.exists():
        print(f"  SRT not found: {srt_file}")
        print("  Run the alignment first: python -m miningcat align")
        return False
    return export_still_video(frame, audio_file, srt_file, output_file, paths.temp, preset, subtitle_lang)


def run(chapter_num: int | None = None, all_chapters: bool = False, preset: str = "ultrafast",
        subtitle_lang: str = "zho") -> None:
    """Exports one chapter (the first by default), or all of them, to output/final."""
    if not paths.chapters_audio.exists():
        raise ConverterError(f"{paths.chapters_audio} not found - run 'audio' first")
    chapter_files = chapter_audio_files()
    paths.final.mkdir(parents=True, exist_ok=True)
    book_title = epub_title()
    titles = chapter_titles()

    def frame_for(audio_file: Path, number: int) -> Path:
        return video_frame(book_title=book_title, chapter_title=titles.get(number), chapter_stem=audio_file.stem)

    if all_chapters:
        print(f"Exporting {len(chapter_files)} chapters...\n")
        for i, audio_file in enumerate(tqdm(chapter_files, unit="ch"), start=1):
            export_chapter(audio_file, frame_for(audio_file, i), paths.final / f"chapter_{i:03d}.mp4", preset, subtitle_lang)
        print(f"\nDone: {paths.final}/")
        return

    num = chapter_num or 1
    if num < 1 or num > len(chapter_files):
        raise ConverterError(f"Invalid chapter {num} (1-{len(chapter_files)})")
    audio_file = chapter_files[num - 1]
    output_file = paths.final / f"chapter_{num:03d}.mp4"
    print(f"Exporting chapter {num}: {audio_file.name}")
    if export_chapter(audio_file, frame_for(audio_file, num), output_file, preset, subtitle_lang):
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
