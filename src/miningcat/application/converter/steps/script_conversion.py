"""Script conversion of the subtitles: simplified / traditional (OpenCC), or Taigi's writing systems."""
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.languages import Language
from miningcat.domain.text.script_conversion import (
    ConversionError,
    can_convert,
    convert_srt,
    whisper_script_target,
)


def convert_srt_file(srt_path: Path, source_script: str, target_script: str) -> None:
    if source_script == target_script:
        return
    text = srt_path.read_text(encoding="utf-8")
    srt_path.write_text(convert_srt(text, source_script, target_script), encoding="utf-8")


def convert_srt_dir(source_script: str, target_script: str) -> None:
    """Converts every SRT file of output/srt from one script to another, in place."""
    if source_script == target_script:
        return
    if not can_convert(source_script, target_script):
        raise ConversionError(f"No conversion path from {source_script!r} to {target_script!r}")

    srt_files = sorted(paths.srt.glob("*.srt"))
    if not srt_files:
        print("  no SRT files to convert")
        return

    for srt_path in srt_files:
        convert_srt_file(srt_path, source_script, target_script)
        print(f"  converted: {srt_path.name}")


def normalize_whisper_script(srt_path: Path, language: Language) -> None:
    """Whisper (and Qwen3-ASR) write Chinese in simplified characters: the subtitles are converted to the variant's
    script."""
    target = whisper_script_target(language)
    if target is not None:
        convert_srt_file(srt_path, "s", target)
