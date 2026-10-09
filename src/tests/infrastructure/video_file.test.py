from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miningcat.domain.languages import Language
from miningcat.infrastructure.media import video_file as video


# extract_audio
def test_extract_audio_builds_expected_path(tmp_path):
    video_file = tmp_path / "reel.mp4"
    output_dir = tmp_path / "audio_out"

    mock_stream = MagicMock()
    mock_stream.output.return_value = mock_stream
    mock_stream.overwrite_output.return_value = mock_stream

    with patch("miningcat.infrastructure.media.video_file.ffmpeg.input", return_value=mock_stream) as mock_input:
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

    with patch("miningcat.infrastructure.media.video_file.ffmpeg.input", return_value=mock_stream):
        video.extract_audio(video_file, output_dir, audio_track=2)

    kwargs = mock_stream.output.call_args.kwargs
    assert kwargs["map"] == "0:a:2"


def test_extract_audio_reuses_existing_file(tmp_path, capsys):
    video_file = tmp_path / "reel.mp4"
    output_dir = tmp_path / "audio_out"
    output_dir.mkdir()
    existing = output_dir / "reel.mp3"
    existing.write_bytes(b"already there")

    with patch("miningcat.infrastructure.media.video_file.ffmpeg.input") as mock_input:
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
    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", return_value=probe_result):
        tracks = video.list_audio_tracks(video_file)

    assert tracks == [
        {"index": 0, "language": "eng", "title": "", "channels": 2, "codec": "aac"},
        {"index": 1, "language": "chi", "title": "Mandarin (Taiwan)", "channels": 6, "codec": "ac3"},
    ]


def test_list_audio_tracks_empty_on_probe_error(tmp_path):
    video_file = tmp_path / "movie.mkv"
    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", side_effect=video.ffmpeg.Error("ffprobe", "", "")):
        assert video.list_audio_tracks(video_file) == []


# extract_embedded_subtitles
def test_extract_embedded_subtitles_empty_when_no_subtitle_stream(tmp_path):
    video_file = tmp_path / "movie.mkv"
    probe_result = {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}
    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", return_value=probe_result):
        assert video.extract_embedded_subtitles(video_file, tmp_path) == []


def test_extract_embedded_subtitles_empty_on_probe_error(tmp_path):
    video_file = tmp_path / "movie.mkv"
    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", side_effect=video.ffmpeg.Error("ffprobe", "", "")):
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

    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", return_value=probe_result), \
         patch("miningcat.infrastructure.media.video_file.subprocess.run", side_effect=fake_run):
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

    with patch("miningcat.infrastructure.media.video_file.ffmpeg.probe", return_value=probe_result), \
         patch("miningcat.infrastructure.media.video_file.subprocess.run", side_effect=fake_run):
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
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        ok = video.mux_subtitles(video_file, [(srt_file, "Whisper")], output_file, tmp_path, subtitle_lang="zho")

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert str(video_file) in cmd
    assert "mov_text" in cmd
    assert cmd.count("-i") == 2  # video + one subtitle track
    assert "title=Whisper" in cmd
    assert output_file.parent.exists()


def test_mux_subtitles_multiple_tracks(tmp_path, monkeypatch):
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
            video_file, [(source_srt, "Source"), (whisper_srt, "Whisper")], output_file, tmp_path,
        )

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert cmd.count("-i") == 3  # video + two subtitle tracks
    assert "-map" in cmd and "1:0" in cmd and "2:0" in cmd
    assert "title=Source" in cmd
    assert "title=Whisper" in cmd


def test_mux_subtitles_no_tracks_returns_false(tmp_path):
    ok = video.mux_subtitles(tmp_path / "vid.mp4", [], tmp_path / "out.mp4", tmp_path)
    assert ok is False


def test_mux_subtitles_ffmpeg_failure(tmp_path, monkeypatch):
    video_file = tmp_path / "reel.mp4"
    video_file.touch()
    srt_file = tmp_path / "reel.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    output_file = tmp_path / "out" / "reel.mp4"

    mock_result = MagicMock(returncode=1)
    with patch("subprocess.run", return_value=mock_result):
        ok = video.mux_subtitles(video_file, [(srt_file, "Whisper")], output_file, tmp_path)

    assert ok is False
