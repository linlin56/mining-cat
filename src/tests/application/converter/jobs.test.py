from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miningcat.application.converter import jobs
from miningcat.application.converter.audiobook_request import AudiobookRequest, AudiobookRequestBuilder
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.jobs import AudiobookJob, InstallJob, VideoJob, find_video_srt, run_job
from miningcat.application.converter.modes import ConversionMode
from miningcat.application.converter.video_request import VideoRequestBuilder
from miningcat.config.paths import paths
from miningcat.domain.languages import Language


class Listener:
    def __init__(self):
        self.logs, self.statuses = [], []

    def log(self, text):
        self.logs.append(text)

    def status(self, text, pct):
        self.statuses.append((text, pct))


# find_video_srt
def test_find_video_srt_prefers_whisper_over_ocr_and_source(tmp_path):
    for name in ("abc_source.srt", "abc_ocr.srt", "abc_whisper.srt"):
        (tmp_path / name).write_text("1\n", encoding="utf-8")
    assert find_video_srt(tmp_path) == tmp_path / "abc_whisper.srt"


def test_find_video_srt_takes_the_latest_transcription(tmp_path):
    import os
    for i, name in enumerate(("abc_ocr.srt", "abc_whisper.srt", "abc_qwen.srt")):
        (tmp_path / name).write_text("1\n", encoding="utf-8")
        os.utime(tmp_path / name, (i, i))
    assert find_video_srt(tmp_path) == tmp_path / "abc_qwen.srt"
    os.utime(tmp_path / "abc_whisper.srt", (9, 9))
    assert find_video_srt(tmp_path) == tmp_path / "abc_whisper.srt"


def test_find_video_srt_falls_back_to_ocr_when_no_whisper(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc_ocr.srt").write_text("1\n", encoding="utf-8")
    assert find_video_srt(tmp_path) == tmp_path / "abc_ocr.srt"


def test_find_video_srt_falls_back_to_any_srt(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    assert find_video_srt(tmp_path) == tmp_path / "abc_source.srt"


def test_find_video_srt_none_when_directory_empty(tmp_path):
    assert find_video_srt(tmp_path) is None


# the video job's command line
def video_command(**ocr) -> list[str]:
    builder = VideoRequestBuilder(Language.FRENCH).local_file(Path("/tmp/movie.mp4")).whisper("tiny")
    if ocr:
        builder.ocr(ocr.get("region"), ocr.get("fps"))
    return VideoJob(builder.build()).command()


def test_video_command_runs_the_video_step():
    args = video_command()
    assert args[-7:] == ["video", "--model", "tiny", "--language", "french", "--file", "/tmp/movie.mp4"]
    assert args[1:3] == ["-m", "miningcat"]


def test_video_command_omits_ocr_flags_by_default():
    args = video_command()
    assert "--ocr" not in args and "--ocr-region" not in args and "--ocr-fps" not in args


def test_video_command_adds_ocr_flags():
    args = video_command(region=(0.0, 0.5, 1.0, 0.5), fps=8)
    assert "--ocr" in args
    assert args[args.index("--ocr-region") + 1] == "0.0,0.5,1.0,0.5"
    assert args[args.index("--ocr-fps") + 1] == "8"


def test_video_command_asks_for_second_subtitles():
    builder = VideoRequestBuilder(Language.FRENCH).local_file(Path("/tmp/movie.mp4")).whisper("tiny")
    assert "--second-subs" not in VideoJob(builder.build()).command()
    assert VideoJob(builder.second_subtitles(None).build()).command()[-2:] == ["--second-subs", "main"]
    assert VideoJob(builder.second_subtitles(1).build()).command()[-2:] == ["--second-subs", "1"]


def test_find_video_srt_never_the_translated_subtitles(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc_translated_en.srt").write_text("1\n", encoding="utf-8")
    assert find_video_srt(tmp_path) == tmp_path / "abc_source.srt"


def test_video_request_keeps_ocr_fps_in_range():
    request = VideoRequestBuilder(Language.FRENCH).url("https://youtu.be/x").ocr(fps=99).build()
    assert request.ocr_fps == 12


def test_video_request_needs_a_source():
    with pytest.raises(ConverterError):
        VideoRequestBuilder(Language.FRENCH).build()
    with pytest.raises(ConverterError):
        VideoRequestBuilder(Language.FRENCH).url("  ")
    with pytest.raises(ConverterError, match="region"):
        VideoRequestBuilder(Language.FRENCH).ocr(region=(0, 0, 2, 1))


def test_video_job_returns_the_subtitles(monkeypatch):
    paths.srt.mkdir(parents=True)
    (paths.srt / "movie_whisper.srt").write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(jobs.processes, "run", lambda args, on_line: on_line("ok\n") or 0)
    request = VideoRequestBuilder(Language.FRENCH).local_file(Path("/tmp/movie.mp4")).build()
    listener = Listener()
    assert run_job(VideoJob(request), listener) == (True, paths.srt / "movie_whisper.srt")
    assert "ok\n" in listener.logs and listener.statuses[-1] == ("Done", 100)


def test_failed_step_is_reported(monkeypatch):
    monkeypatch.setattr(jobs.processes, "run", lambda args, on_line: 2)
    request = VideoRequestBuilder(Language.FRENCH).url("https://youtu.be/x").build()
    listener = Listener()
    assert run_job(VideoJob(request), listener) == (False, None)
    assert "[ERROR] Command 'video' failed (code 2)" in "".join(listener.logs)
    assert listener.statuses[-1] == ("Error - check the log.", 0)


def test_install_job_runs_the_install_command(monkeypatch):
    commands = []
    monkeypatch.setattr(jobs.processes, "run", lambda args, on_line: commands.append(args[3:]) or 0)
    listener = Listener()
    assert run_job(InstallJob("taigi"), listener)[0]
    assert commands == [["install-taigi"]] and listener.statuses[-1] == ("Done", 100)


# the audiobook job
def test_audiobook_job_runs_the_steps_of_its_mode(monkeypatch):
    commands = []
    monkeypatch.setattr(jobs.processes, "run", lambda args, on_line: commands.append(args[3:]) or 0)
    converted = []
    monkeypatch.setattr(jobs, "convert_srt_dir", lambda source, target: converted.append((source, target)))
    request = AudiobookRequest(ConversionMode.GENERATE_AUDIO, Language.MANDARIN_TW, voice_id="zh-TW-YunJheNeural",
                               convert_target="s", selected_chapters=[0, 2], total_chapters=3)
    assert run_job(AudiobookJob(request), Listener())[0]
    assert commands == [
        ["epub", "--chapters", "1,3"],
        ["tts", "--voice", "zh-TW-YunJheNeural", "--language", "mandarin_tw"],
        ["export", "--all", "--language", "mandarin_tw"],
    ]
    assert converted == [("tw", "s")]


def test_audiobook_job_copies_the_picked_files_to_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.processes, "run", lambda args, on_line: 0)
    audio = tmp_path / "picked.mp3"
    audio.write_bytes(b"audio")
    request = AudiobookRequest(ConversionMode.GENERATE_SUBTITLES, Language.FRENCH, audio_files=[audio])
    run_job(AudiobookJob(request), Listener())
    assert (paths.audiobook / "picked.mp3").read_bytes() == b"audio"


def test_audiobook_request_checks_what_the_mode_needs(tmp_path):
    with pytest.raises(ConverterError, match="audio file"):
        AudiobookRequestBuilder(ConversionMode.STANDARD, Language.FRENCH).audio([])
    with pytest.raises(ConverterError, match="EPUB or TXT"):
        AudiobookRequestBuilder(ConversionMode.GENERATE_AUDIO, Language.FRENCH).ebook([])
    with pytest.raises(ConverterError, match="voice"):
        AudiobookRequestBuilder(ConversionMode.GENERATE_AUDIO, Language.FRENCH).voice("Nobody")
    book = tmp_path / "book.txt"
    book.write_text("Il était une fois.", encoding="utf-8")
    with pytest.raises(ConverterError, match="chapter"):
        AudiobookRequestBuilder(ConversionMode.GENERATE_AUDIO, Language.FRENCH).ebook([book], [])
    request = (AudiobookRequestBuilder(ConversionMode.GENERATE_AUDIO, Language.FRENCH)
               .audio([]).ebook([book], [0]).voice("Denise - French (France), female").build())
    assert request.voice_id == "fr-FR-DeniseNeural" and request.chapter_numbers is None
