import re
import shutil
import subprocess

import pytest

from miningcat.infrastructure.media import audio_clip

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def quiet_audio(path, layout):
    """4 s of a quiet tone, on every channel of `layout`."""
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=4",
                    "-af", f"volume=0.02,aformat=channel_layouts={layout}", "-c:a", "aac", str(path)], check=True)
    return path


def loudness(path):
    result = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, check=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", result.stderr.decode())[-1])


@pytest.mark.parametrize("layout", ["stereo", "5.1"])
def test_clips_have_the_loudness_of_speech(tmp_path, layout):
    source = quiet_audio(tmp_path / "film.mp4", layout)
    assert loudness(source) < -30
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(audio_clip.cut_mp3(source, 1, 3))
    assert loudness(clip) == pytest.approx(-16, abs=1.5)


def test_the_center_channel_comes_first(tmp_path):
    assert audio_clip._mono_filter(quiet_audio(tmp_path / "film.mp4", "5.1"), 0).startswith("pan=mono|c0<FC")
    assert audio_clip._mono_filter(quiet_audio(tmp_path / "show.mp4", "stereo"), 0).startswith("aformat")
