from pathlib import Path
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


def test_extract_audio_maps_requested_audio_track(tmp_path):
    video_file = tmp_path / "reel.mp4"
    output_dir = tmp_path / "audio_out"

    mock_stream = MagicMock()
    mock_stream.output.return_value = mock_stream
    mock_stream.overwrite_output.return_value = mock_stream

    with patch("video.ffmpeg.input", return_value=mock_stream):
        video.extract_audio(video_file, output_dir, audio_track=2)

    kwargs = mock_stream.output.call_args.kwargs
    assert kwargs["map"] == "0:a:2"


def test_extract_audio_reuses_existing_file(tmp_path, capsys):
    video_file = tmp_path / "reel.mp4"
    output_dir = tmp_path / "audio_out"
    output_dir.mkdir()
    existing = output_dir / "reel.mp3"
    existing.write_bytes(b"already there")

    with patch("video.ffmpeg.input") as mock_input:
        result = video.extract_audio(video_file, output_dir)

    mock_input.assert_not_called()
    assert result == existing
    assert "already extracted" in capsys.readouterr().out


# list_audio_tracks
def test_list_audio_tracks_returns_audio_streams_only(tmp_path):
    video_file = tmp_path / "movie.mkv"
    probe_result = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "codec_name": "mov_text"},
            {
                "codec_type": "audio", "codec_name": "ac3", "channels": 6,
                "tags": {"language": "chi", "title": "Mandarin (Taiwan)"},
            },
        ]
    }
    with patch("video.ffmpeg.probe", return_value=probe_result):
        tracks = video.list_audio_tracks(video_file)

    assert tracks == [
        {"index": 0, "language": "eng", "title": "", "channels": 2, "codec": "aac"},
        {"index": 1, "language": "chi", "title": "Mandarin (Taiwan)", "channels": 6, "codec": "ac3"},
    ]


def test_list_audio_tracks_empty_on_probe_error(tmp_path):
    video_file = tmp_path / "movie.mkv"
    with patch("video.ffmpeg.probe", side_effect=video.ffmpeg.Error("ffprobe", "", "")):
        assert video.list_audio_tracks(video_file) == []


# extract_embedded_subtitles
def test_extract_embedded_subtitles_empty_when_no_subtitle_stream(tmp_path):
    video_file = tmp_path / "movie.mkv"
    probe_result = {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}
    with patch("video.ffmpeg.probe", return_value=probe_result):
        assert video.extract_embedded_subtitles(video_file, tmp_path) == []


def test_extract_embedded_subtitles_empty_on_probe_error(tmp_path):
    video_file = tmp_path / "movie.mkv"
    with patch("video.ffmpeg.probe", side_effect=video.ffmpeg.Error("ffprobe", "", "")):
        assert video.extract_embedded_subtitles(video_file, tmp_path) == []


def test_extract_embedded_subtitles_extracts_all_present(tmp_path):
    video_file = tmp_path / "movie.mkv"
    probe_result = {
        "streams": [
            {"codec_type": "subtitle", "codec_name": "mov_text", "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "codec_name": "mov_text", "tags": {"title": "Mandarin (Taiwan)"}},
        ]
    }

    def fake_run(cmd, capture_output=True, check=False):
        Path(cmd[-1]).write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("video.ffmpeg.probe", return_value=probe_result), \
         patch("video.subprocess.run", side_effect=fake_run):
        result = video.extract_embedded_subtitles(video_file, tmp_path)

    assert result == [
        (tmp_path / "movie_embedded_0.srt", "eng"),
        (tmp_path / "movie_embedded_1.srt", "Mandarin (Taiwan)"),
    ]
    assert all(path.exists() for path, _tag in result)


def test_extract_embedded_subtitles_skips_failed_streams(tmp_path):
    video_file = tmp_path / "movie.mkv"
    probe_result = {
        "streams": [
            {"codec_type": "subtitle", "codec_name": "dvd_subtitle"},
            {"codec_type": "subtitle", "codec_name": "mov_text", "tags": {"language": "eng"}},
        ]
    }

    def fake_run(cmd, capture_output=True, check=False):
        # Only the second stream (index 1) converts successfully
        if cmd[cmd.index("-map") + 1] == "0:s:1":
            Path(cmd[-1]).write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
            return MagicMock(returncode=0)
        return MagicMock(returncode=1)

    with patch("video.ffmpeg.probe", return_value=probe_result), \
         patch("video.subprocess.run", side_effect=fake_run):
        result = video.extract_embedded_subtitles(video_file, tmp_path)

    assert result == [(tmp_path / "movie_embedded_1.srt", "eng")]


# find_platform_subtitles
def test_find_platform_subtitles_found(tmp_path):
    (tmp_path / "abc.mp4").touch()
    (tmp_path / "abc.zh-Hant.srt").write_text("1\n", encoding="utf-8")
    result = video.find_platform_subtitles(tmp_path, "abc")
    assert result == [tmp_path / "abc.zh-Hant.srt"]


def test_find_platform_subtitles_returns_all_matches(tmp_path):
    (tmp_path / "abc.en.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc.fr.srt").write_text("1\n", encoding="utf-8")
    result = video.find_platform_subtitles(tmp_path, "abc")
    assert result == [tmp_path / "abc.en.srt", tmp_path / "abc.fr.srt"]


def test_find_platform_subtitles_none(tmp_path):
    (tmp_path / "abc.mp4").touch()
    assert video.find_platform_subtitles(tmp_path, "abc") == []


def test_find_platform_subtitles_ignores_other_stems(tmp_path):
    (tmp_path / "other.en.srt").write_text("1\n", encoding="utf-8")
    assert video.find_platform_subtitles(tmp_path, "abc") == []


# mux_subtitles
def test_mux_subtitles_single_track(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path)
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ok = video.mux_subtitles(video_file, [(srt_file, "Whisper")], output_file, subtitle_lang="zho")

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert str(video_file) in cmd
    assert "mov_text" in cmd
    assert cmd.count("-i") == 2  # video + one subtitle track
    assert "title=Whisper" in cmd
    assert output_file.parent.exists()


def test_mux_subtitles_multiple_tracks(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path)
    video_file = tmp_path / "vid.mp4"
    video_file.touch()
    source_srt = tmp_path / "source.srt"
    source_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nsource\n", encoding="utf-8")
    whisper_srt = tmp_path / "whisper.srt"
    whisper_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nwhisper\n", encoding="utf-8")
    output_file = tmp_path / "out" / "vid.mp4"

    mock_result = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ok = video.mux_subtitles(
            video_file, [(source_srt, "Source"), (whisper_srt, "Whisper")], output_file,
        )

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert cmd.count("-i") == 3  # video + two subtitle tracks
    assert "-map" in cmd and "1:0" in cmd and "2:0" in cmd
    assert "title=Source" in cmd
    assert "title=Whisper" in cmd


def test_mux_subtitles_no_tracks_returns_false(tmp_path):
    ok = video.mux_subtitles(tmp_path / "vid.mp4", [], tmp_path / "out.mp4")
    assert ok is False


def test_mux_subtitles_ffmpeg_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path)
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=1)
    with patch("subprocess.run", return_value=mock_result):
        ok = video.mux_subtitles(video_file, [(srt_file, "Whisper")], output_file)

    assert ok is False


# run (full pipeline, all steps mocked)
def _make_pipeline_mocks(tmp_path, call_order):
    video_file = tmp_path / "videos" / "abc.mp4"

    mock_download = MagicMock(return_value=video_file)

    def fake_extract_audio(video_file, output_dir, audio_track=None):
        call_order.append("extract_audio")
        return tmp_path / "temp" / "abc.mp3"
    mock_extract_audio = MagicMock(side_effect=fake_extract_audio)

    mock_extract_embedded_subtitles = MagicMock(return_value=[])

    def fake_mux(video_file, subtitle_tracks, output_file, subtitle_lang="zho"):
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
        extract_embedded_subtitles=mock_extract_embedded_subtitles,
        mux=mock_mux,
        stable_whisper=mock_stable_whisper,
        align=mock_align,
        chinese_converter=mock_chinese_converter,
    )


def _patched_modules(m):
    return patch.dict("sys.modules", {
        "stable_whisper": m["stable_whisper"],
        "align": m["align"],
        "chinese_converter": m["chinese_converter"],
    })


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
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run("https://www.instagram.com/reel/xxx/", model_name="tiny", language=Language.MANDARIN_TW)

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
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    previous_srt = tmp_path / "srt" / "abc_whisper.srt"
    previous_srt.parent.mkdir(parents=True, exist_ok=True)
    previous_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nold transcription\n", encoding="utf-8")

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run("https://www.instagram.com/reel/xxx/", model_name="tiny", language=Language.MANDARIN_TW)

    # Still re-transcribes rather than skipping...
    m["align"].transcribe_chapter.assert_called_once()
    # ...but logs that it's about to overwrite a previous transcription
    out = capsys.readouterr().out
    assert "previous transcription" in out.lower()
    assert str(previous_srt) in out


def test_run_includes_platform_subtitle_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    # Simulate a YouTube caption file written alongside the video by yt-dlp
    (tmp_path / "videos").mkdir(parents=True, exist_ok=True)
    (tmp_path / "videos" / "abc.zh-Hant.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nyoutube caption\n", encoding="utf-8",
    )

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run("https://www.youtube.com/watch?v=xxx", model_name="tiny", language=Language.MANDARIN_TW)

    # Whisper still ran even though a platform track was found
    m["align"].transcribe_chapter.assert_called_once()
    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source", "Whisper"]
    assert (tmp_path / "srt" / "abc_source.srt").exists()
    assert (tmp_path / "srt" / "abc_source.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nyoutube caption\n"


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
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.MANDARIN_TW, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_called_once_with("tw", "s")
    assert call_order.index("convert") < call_order.index("mux")


def test_run_uses_local_video_path_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    m["download"].assert_not_called()
    m["extract_audio"].assert_called_once_with(local_video, tmp_path / "temp", audio_track=None)
    tracks = m["mux"].call_args[0][1]
    assert len(tracks) == 1
    assert tracks[0][1] == "Whisper"


def test_run_local_video_reuses_sibling_srt(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()
    (local_dir / "movie.en.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nexisting subs\n", encoding="utf-8",
    )

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source", "Whisper"]
    assert (tmp_path / "srt" / "movie_source.srt").exists()


def test_run_local_video_keeps_all_sibling_subtitles(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

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

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source (en)", "Source (fr)", "Whisper"]
    assert (tmp_path / "srt" / "movie_source_0.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nenglish\n"
    assert (tmp_path / "srt" / "movie_source_1.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nfrench\n"
    # extracting embedded streams is skipped entirely once sidecar files are found
    m["extract_embedded_subtitles"].assert_not_called()


def test_run_local_video_keeps_all_embedded_subtitles_when_no_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

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

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(model_name="tiny", language=Language.MANDARIN_TW, video_path=local_video)

    tracks = m["mux"].call_args[0][1]
    assert [title for _, title in tracks] == ["Source (eng)", "Source (fre)", "Whisper"]
    assert (tmp_path / "srt" / "movie_source_0.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nembedded en\n"
    assert (tmp_path / "srt" / "movie_source_1.srt").read_text(encoding="utf-8") == \
        "1\n00:00:00,000 --> 00:00:01,000\nembedded fr\n"


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
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         _patched_modules(m):
        video.run(
            "https://www.instagram.com/reel/xxx/", model_name="tiny",
            language=Language.JAPANESE, convert_target="s",
        )

    m["chinese_converter"].convert_srt_dir.assert_not_called()


# run() - OCR mode (replaces Whisper entirely)
def test_run_ocr_skips_whisper_and_produces_ocr_track(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    mock_generate_segments = MagicMock(return_value=[])
    fake_ocr_pipeline_module = MagicMock(generate_segments=mock_generate_segments)

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         patch.dict("sys.modules", {"ocr_mining.pipeline": fake_ocr_pipeline_module}), \
         _patched_modules(m):
        video.run(
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
    monkeypatch.setattr(video, "DIR_VIDEOS", tmp_path / "videos")
    monkeypatch.setattr(video, "DIR_TEMP", tmp_path / "temp")
    monkeypatch.setattr(video, "DIR_SRT", tmp_path / "srt")
    monkeypatch.setattr(video, "DIR_FINAL", tmp_path / "final")

    call_order: list[str] = []
    m = _make_pipeline_mocks(tmp_path, call_order)
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    local_video = local_dir / "movie.mp4"
    local_video.touch()

    mock_generate_segments = MagicMock(return_value=[])
    fake_ocr_pipeline_module = MagicMock(generate_segments=mock_generate_segments)

    with patch("video_downloader.download_video", m["download"]), \
         patch("video.extract_audio", m["extract_audio"]), \
         patch("video.mux_subtitles", m["mux"]), \
         patch("video.extract_embedded_subtitles", m["extract_embedded_subtitles"]), \
         patch.dict("sys.modules", {"ocr_mining.pipeline": fake_ocr_pipeline_module}), \
         _patched_modules(m):
        video.run(
            language=Language.MANDARIN_TW, video_path=local_video,
            use_ocr=True, ocr_region=(0.0, 0.5, 1.0, 0.5), ocr_fps=8,
        )

    mock_generate_segments.assert_called_once_with(
        local_video, language=Language.MANDARIN_TW, region=(0.0, 0.5, 1.0, 0.5), fps=8,
    )
