import subprocess
from pathlib import Path

import ffmpeg

from miningcat.infrastructure.media.ffmpeg_command import FfmpegCommand, link_or_copy


def audio_duration(audio_file: Path) -> float:
    return float(ffmpeg.probe(str(audio_file))["format"]["duration"])


def export_still_video(image: Path, audio_file: Path, srt_file: Path, output_file: Path, scratch_dir: Path,
                       preset: str = "ultrafast", subtitle_lang: str = "zho") -> bool:
    """An MP4 of a still image over the audio, with the subtitles as a text track. Returns whether ffmpeg
    succeeded."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    duration = audio_duration(audio_file)
    srt_link = link_or_copy(srt_file, scratch_dir / "subs.srt")
    cmd = (
        FfmpegCommand()
        .input(image, "-loop", "1", "-framerate", "1")
        .input(audio_file)
        .input(srt_link.absolute())
        .codec("v", "libx264").option("-preset", preset, "-pix_fmt", "yuv420p")
        .codec("a", "aac").option("-b:a", "128k")
        .codec("s", "mov_text")
        .metadata("s:s:0", "language", subtitle_lang)
        .option("-t", str(duration))
        .overwrite()
        .build(output_file)
    )
    result = subprocess.run(cmd, check=False)
    srt_link.unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"  FFmpeg error (code {result.returncode})")
        return False
    return True
