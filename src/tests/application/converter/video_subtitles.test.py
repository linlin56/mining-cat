import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miningcat.application.converter import video_subtitles as video
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.video_request import VideoRequestBuilder
from miningcat.domain.languages import Language

from shared import redirect_path


def run_video(url=None, model_name="tiny", language=Language.MANDARIN_TW, app_id="web", convert_target=None,
              video_path=None, audio_track=None, use_ocr=False, ocr_region=None, ocr_fps=None):
    builder = VideoRequestBuilder(language).whisper(model_name).convert_to(convert_target)
    if video_path is not None:
        builder.local_file(video_path, audio_track)
    else:
        builder.url(url, app_id)
    if use_ocr:
        builder.ocr(ocr_region, ocr_fps)
    return video.run(builder.build())


# run (full pipeline, all steps mocked)
def _make_pipeline_mocks(tmp_path, call_order):
    video_file = tmp_path / "videos" / "abc.mp4"

    mock_download = MagicMock(return_value=video_file)

    def fake_extract_audio(video_file, output_dir, audio_track=None):
        call_order.append("extract_audio")
        return tmp_path / "temp" / "abc.mp3"
    mock_extract_audio = MagicMock(side_effect=fake_extract_audio)

    mock_extract_embedded_subtitles = MagicMock(return_value=[])

    def fake_mux(video_file, subtitle_tracks, output_file, scratch_dir, subtitle_lang="zho"):
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
        return ["segment"]
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
        extract_embedded_subtitles=mock_extract_embedded_subtitles,
        mux=mock_mux,
        stable_whisper=mock_stable_whisper,
        align=mock_align,
        chinese_converter=mock_chinese_converter,
    )


def _patched_modules(m):
    stack = contextlib.ExitStack()
    m["stable_whisper"].load_model.return_value.name = "Whisper"
    stack.enter_context(patch.object(video.speech_engines, "load_transcriber",
                                     lambda name, lang: m["stable_whisper"].load_model(name)))
    stack.enter_context(patch.object(video.transcription, "transcribe", m["align"].transcribe_chapter))
    stack.enter_context(patch.object(video, "save_srt", m["align"].save_srt))
    stack.enter_context(patch.object(video, "convert_srt_dir", m["chinese_converter"].convert_srt_dir))
    stack.enter_context(patch.object(video, "normalize_whisper_script", MagicMock()))
    return stack


def test_run_orchestrates_pipeline(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video("https://www.instagram.com/reel/xxx/", model_name="tiny", language=Language.MANDARIN_TW)

    m["download"].assert_called_once()
    m["extract_audio"].assert_called_once()
    m["align"].transcribe_chapter.assert_called_once()
    m["mux"].assert_called_once()
    # No platform subtitle exists (Instagram) -> only the Whisper track is muxed
    tracks = m["mux"].call_args[0][1]
    assert len(tracks) == 1
    assert tracks[0][1] == "Whisper"
    assert tracks[0][0].name == "abc_whisper.srt"
    m["chinese_converter"].convert_srt_dir.assert_not_called()


def test_run_logs_and_overwrites_previous_transcription(tmp_path, monkeypatch, capsys):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    previous_srt = tmp_path / "srt" / "abc_whisper.srt"
    previous_srt.parent.mkdir(parents=True, exist_ok=True)
    previous_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nold transcription\n", encoding="utf-8")

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video("https://www.instagram.com/reel/xxx/", model_name="tiny", language=Language.MANDARIN_TW)

    # Still re-transcribes rather than skipping...
    m["align"].transcribe_chapter.assert_called_once()
    # ...but logs that it's about to overwrite a previous transcription
    out = capsys.readouterr().out
    assert "previous transcription" in out.lower()
    assert str(previous_srt) in out


def test_run_includes_platform_subtitle_when_present(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    # Simulate a YouTube caption file written alongside the video by yt-dlp
    (tmp_path / "videos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "videos" / "abc.zh-Hant.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nyoutube caption\n", encoding="utf-8",
    )

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video("https://www.youtube.com/watch?v=xxx", model_name="tiny", language=Language.MANDARIN_TW)

    # Whisper still ran even though a platform track was found
    m["align"].transcribe_chapter.assert_called_once()
    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source", "Whisper"]
    assert (tmp_path / "srt" / "abc_source.srt").exists()
    assert (tmp_path / "srt" / "abc_source.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nyoutube caption\n"


def test_run_applies_conversion_before_mux(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.MANDARIN_TW, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_called_once_with("tw", "s")
    assert call_order.index("convert") < call_order.index("mux")


def test_run_uses_local_video_path_without_downloading(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    m["download"].assert_not_called()
    m["extract_audio"].assert_called_once_with(local_video, tmp_path / "temp", audio_track=None)
    tracks = m["mux"].call_args[0][1]
    assert len(tracks) == 1
    assert tracks[0][1] == "Whisper"


def test_run_local_video_reuses_sibling_srt(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()
    (local_dir / "movie.en.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nexisting subs\n", encoding="utf-8",
    )

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source", "Whisper"]
    assert (tmp_path / "srt" / "movie_source.srt").exists()


def test_run_local_video_keeps_all_sibling_subtitles(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()
    (local_dir / "movie.en.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nenglish\n", encoding="utf-8",
    )
    (local_dir / "movie.fr.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nfrench\n", encoding="utf-8",
    )

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source (en)", "Source (fr)", "Whisper"]
    assert (tmp_path / "srt" / "movie_source_0.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nenglish\n"
    assert (tmp_path / "srt" / "movie_source_1.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nfrench\n"
    # extracting embedded streams is skipped entirely once sidecar files are found
    m["extract_embedded_subtitles"].assert_not_called()


def test_run_local_video_keeps_all_embedded_subtitles_when_no_sidecar(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mkv"
    local_video.touch()

    embedded_en = tmp_path / "temp" / "movie_embedded_0.srt"
    embedded_fr = tmp_path / "temp" / "movie_embedded_1.srt"
    m["extract_embedded_subtitles"].return_value = [(embedded_en, "eng"), (embedded_fr, "fre")]
    embedded_en.parent.mkdir(parents=True, exist_ok=True)
    embedded_en.write_text("1\n00:00:00,000 --> 00:00:01,000\nembedded en\n", encoding="utf-8")
    embedded_fr.write_text("1\n00:00:00,000 --> 00:00:01,000\nembedded fr\n", encoding="utf-8")

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source (eng)", "Source (fre)", "Whisper"]
    assert (tmp_path / "srt" / "movie_source_0.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nembedded en\n"
    assert (tmp_path / "srt" / "movie_source_1.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nembedded fr\n"


def test_run_skips_conversion_for_unsupported_language(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        run_video(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.JAPANESE, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_not_called()


# run() - OCR mode (replaces Whisper entirely)
def test_run_ocr_skips_whisper_and_produces_ocr_track(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    mock_generate_segments = MagicMock(return_value=["segment"])
    fake_ocr_pipeline_module = MagicMock(generate_segments=mock_generate_segments)

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         patch.object(video, "generate_segments", fake_ocr_pipeline_module.generate_segments), \
         _patched_modules(m):
        run_video(
            language=Language.MANDARIN_TW, video_path=local_video,
            use_ocr=True, ocr_region=(0.0, 0.5, 1.0, 0.5),
        )

    m["download"].assert_not_called()
    m["extract_audio"].assert_not_called()
    m["align"].transcribe_chapter.assert_not_called()
    mock_generate_segments.assert_called_once_with(
        local_video, language=Language.MANDARIN_TW, region=(0.0, 0.5, 1.0, 0.5), fps=4,
    )
    tracks = m["mux"].call_args[0][1]
    assert len(tracks) == 1
    assert tracks[0][1] == "OCR"
    assert tracks[0][0].name == "movie_ocr.srt"


def test_run_ocr_passes_custom_fps(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path / "videos")
    redirect_path(monkeypatch, "temp", tmp_path / "temp")
    redirect_path(monkeypatch, "srt", tmp_path / "srt")
    redirect_path(monkeypatch, "final", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    mock_generate_segments = MagicMock(return_value=["segment"])
    fake_ocr_pipeline_module = MagicMock(generate_segments=mock_generate_segments)

    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         patch.object(video, "generate_segments", fake_ocr_pipeline_module.generate_segments), \
         _patched_modules(m):
        run_video(
            language=Language.MANDARIN_TW, video_path=local_video,
            use_ocr=True, ocr_region=(0.0, 0.5, 1.0, 0.5), ocr_fps=8,
        )

    mock_generate_segments.assert_called_once_with(
        local_video, language=Language.MANDARIN_TW, region=(0.0, 0.5, 1.0, 0.5), fps=8,
    )


# An empty transcription isn't muxed (ffmpeg can't read an empty .srt): with nothing else to add, the run fails.
def test_run_fails_without_any_subtitles(tmp_path, monkeypatch, capsys):
    m = _make_pipeline_mocks(tmp_path, [])
    m["align"].transcribe_chapter.side_effect = lambda model, audio_file, lang: []
    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", m["mux"]), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m), pytest.raises(ConverterError, match="No subtitles"):
        run_video("https://www.instagram.com/reel/xxx/", language=Language.MANDARIN_TW)
    m["mux"].assert_not_called()
    assert "Nothing transcribed" in capsys.readouterr().out


def test_run_fails_when_muxing_fails(tmp_path, monkeypatch):
    m = _make_pipeline_mocks(tmp_path, [])
    with patch.object(video, "download_video", m["download"]), \
         patch.object(video, "extract_audio", m["extract_audio"]), \
         patch.object(video, "mux_subtitles", MagicMock(return_value=False)), \
         patch("miningcat.infrastructure.media.video_file.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m), pytest.raises(ConverterError, match="Could not add"):
        run_video("https://www.instagram.com/reel/xxx/", language=Language.MANDARIN_TW)
