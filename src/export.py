import json
import os
import shutil
import subprocess
from pathlib import Path

import ffmpeg
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

import epub as epub_module
from config import DIR_CHAPTERS_AUDIO, DIR_FINAL, DIR_SRT, DIR_TEMP, FONT_CANDIDATES


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fit_font(draw: ImageDraw.ImageDraw, text: str, base_size: int, max_width: int, min_size: int = 12) -> ImageFont.FreeTypeFont:
    size = base_size
    while size >= min_size:
        font = _load_font(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return _load_font(min_size)


def _draw_text_overlay(
    frame: Image.Image,
    book_title: str | None,
    chapter_title: str | None,
    width: int,
    height: int,
) -> Image.Image:
    lines_spec = []
    if book_title:
        lines_spec.append((book_title, 34, (255, 255, 255, 255)))
    if chapter_title:
        lines_spec.append((chapter_title, 26, (200, 200, 200, 255)))
    if not lines_spec:
        return frame

    max_text_w = width // 4
    padding = 18
    margin = 28
    line_gap = 8

    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    rendered = []
    for text, size, color in lines_spec:
        font = _fit_font(draw, text, size, max_text_w - 2 * padding)
        bbox = draw.textbbox((0, 0), text, font=font)
        rendered.append((text, font, color, bbox[2] - bbox[0], bbox[3] - bbox[1]))

    box_w = max(tw for *_, tw, _ in rendered) + 2 * padding
    box_h = sum(th for *_, th in rendered) + line_gap * (len(rendered) - 1) + 2 * padding

    x0, y0 = margin, margin
    draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=8, fill=(0, 0, 0, 160))

    y = y0 + padding
    for text, font, color, _, lh in rendered:
        draw.text((x0 + padding, y), text, font=font, fill=color)
        y += lh + line_gap

    return Image.alpha_composite(frame.convert('RGBA'), overlay).convert('RGB')


def create_video_frame(
    width: int = 1920,
    height: int = 1080,
    book_title: str | None = None,
    chapter_title: str | None = None,
    chapter_stem: str | None = None,
) -> Path:
    cache_key = chapter_stem or "default"
    output_path = DIR_TEMP / f"video_frame_{cache_key}.png"
    if output_path.exists():
        return output_path

    frame = Image.new('RGB', (width, height), color='black')

    cover_path = epub_module.get_epub_cover()
    if cover_path:
        try:
            cover = Image.open(cover_path).convert('RGB')
            cover.thumbnail((width, height), Image.LANCZOS)
            x = (width - cover.width) // 2
            y = (height - cover.height) // 2
            frame.paste(cover, (x, y))
        except Exception:
            pass

    frame = _draw_text_overlay(frame, book_title, chapter_title, width, height)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.save(output_path)
    return output_path


def _load_chapter_titles() -> dict[int, str]:
    manifest_path = DIR_TEMP / "ebook_chapters.json"
    if not manifest_path.exists():
        return {}
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {e["index"]: e["title"] for e in entries if "index" in e and "title" in e}
    except Exception:
        return {}


def get_chapter_audio_files() -> list[Path]:
    files = sorted(DIR_CHAPTERS_AUDIO.glob("*.mp3"))
    if not files:
        raise FileNotFoundError(f"No .mp3 found in {DIR_CHAPTERS_AUDIO}")
    return files


def get_audio_duration(audio_file: Path) -> float:
    probe = ffmpeg.probe(str(audio_file))
    return float(probe['format']['duration'])


def export_chapter_to_mp4(
    audio_file: Path,
    video_frame: Path,
    output_file: Path,
    preset: str = "ultrafast",
    subtitle_lang: str = "zho",
) -> bool:
    srt_file = DIR_SRT / (audio_file.stem + ".srt")
    if not srt_file.exists():
        print(f"  SRT not found: {srt_file}")
        print(f"  Run first: main.py align --only {audio_file.stem}")
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    audio_duration = get_audio_duration(audio_file)

    srt_link = Path("subs.srt")
    if srt_link.exists():
        srt_link.unlink()
    try:
        # symlink to fix ffmpeg issues with some paths
        os.symlink(srt_file.absolute(), srt_link.absolute())
    except (OSError, NotImplementedError):
        shutil.copy(srt_file, srt_link)

    cmd = [
        'ffmpeg',
        '-loop', '1', '-framerate', '1', '-i', str(video_frame),
        '-i', str(audio_file),
        '-i', str(srt_link.absolute()),
        '-c:v', 'libx264', '-preset', preset, '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k',
        '-c:s', 'mov_text',
        '-metadata:s:s:0', f'language={subtitle_lang}',
        '-t', str(audio_duration),
        '-y',
        str(output_file),
    ]

    result = subprocess.run(cmd, check=False)

    if srt_link.exists():
        srt_link.unlink()

    if result.returncode != 0:
        print(f"  FFmpeg error (code {result.returncode})")
        return False
    return True


def run(
    chapter_num: int | None = None,
    all_chapters: bool = False,
    preset: str = "ultrafast",
    subtitle_lang: str = "zho",
) -> None:
    import sys

    if not DIR_CHAPTERS_AUDIO.exists():
        print(f"Error: {DIR_CHAPTERS_AUDIO} not found - run 'audio' first")
        sys.exit(1)

    chapter_files = get_chapter_audio_files()
    DIR_FINAL.mkdir(parents=True, exist_ok=True)

    book_title = epub_module.get_epub_title()
    chapter_titles = _load_chapter_titles()

    def _frame_for(audio_file: Path, idx: int) -> Path:
        return create_video_frame(
            book_title=book_title,
            chapter_title=chapter_titles.get(idx),
            chapter_stem=audio_file.stem,
        )

    if all_chapters:
        print(f"Exporting {len(chapter_files)} chapters...\n")
        for i, audio_file in enumerate(tqdm(chapter_files, unit="ch"), start=1):
            output_file = DIR_FINAL / f"chapter_{i:03d}.mp4"
            export_chapter_to_mp4(audio_file, _frame_for(audio_file, i), output_file, preset, subtitle_lang)
        print(f"\nDone: {DIR_FINAL}/")
    else:
        num = chapter_num or 1
        if num < 1 or num > len(chapter_files):
            print(f"Invalid chapter {num} (1-{len(chapter_files)})")
            sys.exit(1)
        audio_file = chapter_files[num - 1]
        output_file = DIR_FINAL / f"chapter_{num:03d}.mp4"
        print(f"Exporting chapter {num}: {audio_file.name}")
        if export_chapter_to_mp4(audio_file, _frame_for(audio_file, num), output_file, preset, subtitle_lang):
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"\nOK: {output_file}  ({size_mb:.1f} MB)")
