from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import video_downloader


def test_download_video_dispatches_to_handler(tmp_path):
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch("video_downloader.get_handler", return_value=mock_handler):
        result = video_downloader.download_video("https://www.instagram.com/reel/xxx/", tmp_path)

    mock_handler.download.assert_called_once_with("https://www.instagram.com/reel/xxx/", tmp_path)
    assert result == tmp_path / "video.mp4"


def test_download_video_passes_options(tmp_path):
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch("video_downloader.get_handler", return_value=mock_handler):
        video_downloader.download_video("https://www.instagram.com/reel/xxx/", tmp_path, app_id="ios")

    mock_handler.download.assert_called_once_with(
        "https://www.instagram.com/reel/xxx/", tmp_path, app_id="ios"
    )


def test_download_video_defaults_to_dir_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(video_downloader, "DIR_VIDEOS", tmp_path)
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch("video_downloader.get_handler", return_value=mock_handler):
        video_downloader.download_video("https://www.instagram.com/reel/xxx/")

    mock_handler.download.assert_called_once_with("https://www.instagram.com/reel/xxx/", tmp_path)


def test_download_video_unknown_host_raises(tmp_path):
    with pytest.raises(ValueError):
        video_downloader.download_video("https://www.youtube.com/watch?v=xxx", tmp_path)
