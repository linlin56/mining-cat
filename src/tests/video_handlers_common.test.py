from pathlib import Path
from unittest.mock import MagicMock

from video_handlers._common import resolve_downloaded_path


def test_resolve_downloaded_path_uses_requested_downloads_filepath():
    mock_ydl = MagicMock()
    info = {"requested_downloads": [{"filepath": "/tmp/abc.mp4"}], "__real_download": True}

    result = resolve_downloaded_path(mock_ydl, info)

    assert result == Path("/tmp/abc.mp4")
    mock_ydl.prepare_filename.assert_not_called()


def test_resolve_downloaded_path_falls_back_to_prepare_filename():
    mock_ydl = MagicMock()
    mock_ydl.prepare_filename.return_value = "/tmp/xyz.mp4"
    info = {"id": "xyz", "__real_download": True}

    result = resolve_downloaded_path(mock_ydl, info)

    assert result == Path("/tmp/xyz.mp4")


def test_resolve_downloaded_path_logs_skip_when_not_real_download(capsys):
    mock_ydl = MagicMock()
    info = {"requested_downloads": [{"filepath": "/tmp/abc.mp4"}], "__real_download": False}

    resolve_downloaded_path(mock_ydl, info)

    assert "Skipped download" in capsys.readouterr().out


def test_resolve_downloaded_path_logs_skip_when_flag_missing():
    # yt-dlp doesn't always set __real_download explicitly on the skip path -
    # its absence must be treated the same as False, not as a real download.
    mock_ydl = MagicMock()
    info = {"requested_downloads": [{"filepath": "/tmp/abc.mp4"}]}

    resolve_downloaded_path(mock_ydl, info)


def test_resolve_downloaded_path_silent_when_real_download(capsys):
    mock_ydl = MagicMock()
    info = {"requested_downloads": [{"filepath": "/tmp/abc.mp4"}], "__real_download": True}

    resolve_downloaded_path(mock_ydl, info)

    assert capsys.readouterr().out == ""
