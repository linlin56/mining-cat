import os
import shutil
import subprocess
import threading
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

# Pipeline for audiobook/ebook processing: alignment, transcription, TTS, and export
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
                extra += ["--voice", VOICE_ID_BY_LABEL[voice_label], "--language", lang.name.lower()]
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


def _latest_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


# Picks the SRT to use for frequency lists after a video run. Prefers the Whisper
# or OCR transcript (always generated, most complete) over a platform-provided "*_source.srt".
def _find_video_srt(directory: Path) -> Path | None:
    return (_latest_file(directory, "*_whisper.srt")
            or _latest_file(directory, "*_ocr.srt")
            or _latest_file(directory, "*.srt"))


# Pipeline for transcribing a video, either downloaded from an online platform or a local file
def run_video_pipeline(
    *,
    python_exe: str,
    lang: Language,
    model: str,
    convert_target: str | None,
    url: str | None = None,
    video_path: Path | None = None,
    audio_track: int | None = None,
    use_ocr: bool = False,
    ocr_region: tuple[float, float, float, float] | None = None,
    ocr_fps: int | None = None,
    schedule: Callable,
    log: Callable[[str], None],
    set_status: Callable[[str, float], None],
    on_done: Callable[[Path | None], None],
    on_finish: Callable[[], None],
) -> None:
    from config import DIR_SRT

    try:
        if video_path is not None:
            schedule(0, set_status, "Transcribing local video…", 10)
            schedule(0, log, "\nStep 1/1 - Local video subtitles\n")
        else:
            schedule(0, set_status, "Downloading & transcribing video…", 10)
            schedule(0, log, "\nStep 1/1 - Video download + subtitles\n")
        cmd_args = [python_exe, str(SRC_DIR / "main.py"), "video",
                    "--model", model, "--language", lang.name.lower()]
        cmd_args += ["--file", str(video_path)] if video_path is not None else ["--url", url]
        if convert_target is not None:
            cmd_args += ["--convert-to", convert_target]
        if audio_track is not None:
            cmd_args += ["--audio-track", str(audio_track)]
        if use_ocr:
            cmd_args += ["--ocr"]
        if ocr_region is not None:
            cmd_args += ["--ocr-region", ",".join(str(v) for v in ocr_region)]
        if ocr_fps is not None:
            cmd_args += ["--ocr-fps", str(ocr_fps)]
        rc = _run_cmd(cmd_args, schedule=schedule, log=log)
        if rc != 0:
            raise RuntimeError(f"Command 'video' failed (code {rc})")

        srt_path = _find_video_srt(DIR_SRT)

        schedule(0, set_status, "Done", 100)
        schedule(0, log, "\nPipeline complete.\n")
        schedule(0, on_done, srt_path)
    except Exception as exc:
        schedule(0, log, f"\n[ERROR] {exc}\n")
        schedule(0, set_status, "Error - check the log.", 0)
    finally:
        schedule(0, on_finish)


# Starts the video game / screen share capture (`main.py game serve`) and returns right away: it runs until stopped.
# Stop it with stop_game_server(). `on_exit(returncode)` is scheduled once the process has ended, whatever the reason.
def start_game_server(
    *,
    python_exe: str,
    lang: Language,
    convert_target: str | None,
    continuous: bool,
    hotkey: str,
    schedule: Callable,
    log: Callable[[str], None],
    on_exit: Callable[[int], None],
) -> subprocess.Popen:
    cmd_args = [python_exe, str(SRC_DIR / "main.py"), "game", "serve", "--language", lang.name.lower()]
    if convert_target is not None:
        cmd_args += ["--convert-to", convert_target]
    cmd_args += ["--continuous"] if continuous else ["--hotkey", hotkey]
    proc = _popen(cmd_args)

    def pump() -> None:
        for line in proc.stdout:
            schedule(0, log, line)
        schedule(0, on_exit, proc.wait())

    threading.Thread(target=pump, daemon=True).start()
    return proc


# SIGTERM lets aiohttp shut down cleanly (and close the capture session), kill if it doesn't in time.
def stop_game_server(proc: subprocess.Popen, timeout: float = 5) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def _popen(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(SRC_DIR),
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
        encoding="utf-8",
    )


def _run_cmd(
    args: list[str],
    *,
    schedule: Callable,
    log: Callable[[str], None],
) -> int:
    proc = _popen(args)
    for line in proc.stdout:
        schedule(0, log, line)
    proc.wait()
    return proc.returncode
