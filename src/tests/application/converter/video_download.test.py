from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from miningcat.application.converter import video_download as video_downloader

from shared import redirect_path


def test_download_video_dispatches_to_handler(tmp_path):
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch.object(video_downloader, "get_handler", return_value=mock_handler):
        result = video_downloader.download_video("https://www.instagram.com/reel/xxx/", tmp_path)

    mock_handler.download.assert_called_once_with("https://www.instagram.com/reel/xxx/", tmp_path)
    assert result == tmp_path / "video.mp4"


def test_download_video_passes_options(tmp_path):
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch.object(video_downloader, "get_handler", return_value=mock_handler):
        video_downloader.download_video("https://www.instagram.com/reel/xxx/", tmp_path, app_id="ios")

    mock_handler.download.assert_called_once_with(
        "https://www.instagram.com/reel/xxx/", tmp_path, app_id="ios"
    )


def test_download_video_defaults_to_dir_videos(tmp_path, monkeypatch):
    redirect_path(monkeypatch, "videos", tmp_path)
    mock_handler = MagicMock()
    mock_handler.download.return_value = tmp_path / "video.mp4"

    with patch.object(video_downloader, "get_handler", return_value=mock_handler):
        video_downloader.download_video("https://www.instagram.com/reel/xxx/")

    mock_handler.download.assert_called_once_with("https://www.instagram.com/reel/xxx/", tmp_path)


def test_download_video_unknown_host_raises(tmp_path):
    with pytest.raises(ValueError):
        video_downloader.download_video("https://www.tiktok.com/@user/video/xxx", tmp_path)
