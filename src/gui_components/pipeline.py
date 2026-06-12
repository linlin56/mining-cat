import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import chinese_converter
from language import Language
from gui_components.constants import (
    DIR_AUDIOBOOK, DIR_EBOOK, SRC_DIR,
    STEPS, STEPS_WHISPER, STEPS_TTS,
    VOICE_ID_BY_LABEL,
)


def _clear_dir(path: Path) -> None:
    if path.exists():
        for f in path.iterdir():
            if f.is_file():
                f.unlink()
    else:
        path.mkdir(parents=True, exist_ok=True)


def copy_sources(
    *,
    mode: str,
    audio_files: list[Path],
    epub_files: list[Path],
    log: Callable[[str], None],
) -> None:
    log("Copying source files\n")
    if mode != "Generate audio":
        audio_outside = [f for f in audio_files if f.parent != DIR_AUDIOBOOK]
        if audio_outside:
            _clear_dir(DIR_AUDIOBOOK)
            for f in audio_files:
                shutil.copy2(f, DIR_AUDIOBOOK / f.name)
                log(f"  audio : {f.name}\n")
        else:
            log("  audio : files already in place\n")

    if mode != "Generate subtitles" and epub_files:
        outside = [f for f in epub_files if f.parent != DIR_EBOOK]
        if outside:
            _clear_dir(DIR_EBOOK)
            for f in epub_files:
                shutil.copy2(f, DIR_EBOOK / f.name)
                log(f"  ebook : {f.name}\n")
        else:
            log(f"  ebook : file(s) already in place\n")


def run_pipeline(
    *,
    python_exe: str,
    mode: str,
    lang: Language,
    model: str,
    convert_target: str | None,
    voice_label: str,
    audio_files: list[Path],
    epub_files: list[Path],
    epub_chapters: list[tuple[str, str]],
    selected_chapters: list[int],
    schedule: Callable,
    log: Callable[[str], None],
    set_status: Callable[[str, float], None],
    on_done: Callable[[], None],
    on_finish: Callable[[], None],
) -> None:
    if mode == "Standard":
        steps = STEPS
    elif mode == "Generate subtitles":
        steps = STEPS_WHISPER
    else:
        steps = STEPS_TTS

    try:
        copy_sources(mode=mode, audio_files=audio_files, epub_files=epub_files, log=log)
        for label, pct_start, cmd, extra in steps:
            extra = list(extra)
            if cmd == "epub":
                total = len(epub_chapters)
                if selected_chapters and len(selected_chapters) < total:
                    extra += ["--chapters", ",".join(str(i + 1) for i in selected_chapters)]
            elif cmd in ("align", "transcribe"):
                extra += ["--language", lang.name.lower(), "--model", model]
            elif cmd == "export":
                extra += ["--language", lang.name.lower()]
            elif cmd == "tts":
                extra += ["--voice", VOICE_ID_BY_LABEL[voice_label]]
            schedule(0, set_status, label + "…", pct_start)
            schedule(0, log, f"\n{label}\n")
            rc = _run_cmd([python_exe, str(SRC_DIR / "main.py"), cmd] + extra,
                          schedule=schedule, log=log)
            if rc != 0:
                raise RuntimeError(f"Command '{cmd}' failed (code {rc})")
            if cmd in ("align", "tts") and convert_target is not None:
                source = chinese_converter.SCRIPT_FOR_LANGUAGE[lang]
                schedule(0, set_status, "Step 3.5 - Character conversion…", 45)
                schedule(0, log, "\nStep 3.5 - Character conversion\n")
                chinese_converter.convert_srt_dir(source, convert_target)
                schedule(0, log, "  Done.\n")
        schedule(0, set_status, "Done", 100)
        schedule(0, log, "\nPipeline complete.\n")
        schedule(0, on_done)
    except Exception as exc:
        schedule(0, log, f"\n[ERROR] {exc}\n")
        schedule(0, set_status, "Error - check the log.", 0)
    finally:
        schedule(0, on_finish)


def _run_cmd(
    args: list[str],
    *,
    schedule: Callable,
    log: Callable[[str], None],
) -> int:
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(SRC_DIR),
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
        encoding="utf-8",
    )
    for line in proc.stdout:
        schedule(0, log, line)
    proc.wait()
    return proc.returncode
