from unittest.mock import patch, MagicMock

import video
from language import Language


# extract_audio
def test_extract_audio_builds_expected_path(tmp_path):
    video_file = tmp_path / "reel.mp4"
    output_dir = tmp_path / "audio_out"

    mock_stream = MagicMock()
    mock_stream.output.return_value = mock_stream
    mock_stream.overwrite_output.return_value = mock_stream

    with patch("video.ffmpeg.input", return_value=mock_stream) as mock_input:
        result = video.extract_audio(video_file, output_dir)

    mock_input.assert_called_once_with(str(video_file))
    mock_stream.run.assert_called_once()
    assert result == output_dir / "reel.mp3"
    assert output_dir.exists()


# mux_subtitles
def test_mux_subtitles_success(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path)
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ok = video.mux_subtitles(video_file, srt_file, output_file, subtitle_lang="zho")

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert str(video_file) in cmd
    assert "mov_text" in cmd
    assert output_file.parent.exists()


def test_mux_subtitles_ffmpeg_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path)
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=1)
    with patch("subprocess.run", return_value=mock_result):
        ok = video.mux_subtitles(video_file, srt_file, output_file)

    assert ok is False


# run (full pipeline, all steps mocked)
def _make_pipeline_mocks(tmp_path, call_order):
    video_file = tmp_path / "videos" / "abc.mp4"

    mock_download = MagicMock(return_value=video_file)

    def fake_extract_audio(video_file, output_dir):
        call_order.append("extract_audio")
        return tmp_path / "temp" / "abc.mp3"
    mock_extract_audio = MagicMock(side_effect=fake_extract_audio)

    def fake_mux(video_file, srt_file, output_file, subtitle_lang="zho"):
        call_order.append("mux")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"fake")
        return True
    mock_mux = MagicMock(side_effect=fake_mux)

    mock_stable_whisper = MagicMock()

    mock_align = MagicMock()
    mock_align.get_device.return_value = "cpu"

    def fake_transcribe_chapter(model, audio_file, lang):
        call_order.append("transcribe")
        return []
    mock_align.transcribe_chapter.side_effect = fake_transcribe_chapter

    def fake_save_srt(segs, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    mock_align.save_srt.side_effect = fake_save_srt

    mock_chinese_converter = MagicMock()
    mock_chinese_converter.SCRIPT_FOR_LANGUAGE = {Language.MANDARIN_TW: "tw", Language.MANDARIN_CN: "s"}

    def fake_convert_srt_dir(source, target):
        call_order.append("convert")
    mock_chinese_converter.convert_srt_dir.side_effect = fake_convert_srt_dir

    return dict(
        video_file=video_file,
        download=mock_download,
        extract_audio=mock_extract_audio,
        mux=mock_mux,
        stable_whisper=mock_stable_whisper,
        align=mock_align,
        chinese_converter=mock_chinese_converter,
    )


def test_run_orchestrates_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch.dict("sys.modules", {
             "stable_whisper": m["stable_whisper"],
             "align": m["align"],
             "chinese_converter": m["chinese_converter"],
         }):
        video.run("https://www.instagram.com/reel/xxx/", model_name="tiny", language=Language.MANDARIN_TW)

    m["download"].assert_called_once()
    m["extract_audio"].assert_called_once()
    m["align"].transcribe_chapter.assert_called_once()
    m["mux"].assert_called_once()
    m["chinese_converter"].convert_srt_dir.assert_not_called()


def test_run_applies_conversion_before_mux(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch.dict("sys.modules", {
             "stable_whisper": m["stable_whisper"],
             "align": m["align"],
             "chinese_converter": m["chinese_converter"],
         }):
        video.run(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.MANDARIN_TW, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_called_once_with("tw", "s")
    assert call_order.index("convert") < call_order.index("mux")


def test_run_skips_conversion_for_unsupported_language(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch.dict("sys.modules", {
             "stable_whisper": m["stable_whisper"],
             "align": m["align"],
             "chinese_converter": m["chinese_converter"],
         }):
        video.run(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.JAPANESE, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_not_called()
