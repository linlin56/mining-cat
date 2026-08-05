from pathlib import Path
from unittest.mock import patch, MagicMock

import video_handlers.bilibili as bilibili


def test_domains():
    assert "bilibili.com" in bilibili.DOMAINS


def test_download_uses_requested_downloads_filepath(tmp_path):
    fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "abc123.mp4")}]}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_cls:
        result = bilibili.download("https://www.bilibili.com/video/BVxxx", tmp_path)

    assert result == Path(tmp_path / "abc123.mp4")
    opts = mock_cls.call_args[0][0]
    assert "writesubtitles" not in opts


def test_download_falls_back_to_prepare_filename(tmp_path):
    fake_info = {"id": "xyz", "ext": "mp4"}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(tmp_path / "xyz.mp4")
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = bilibili.download("https://www.bilibili.com/video/BVxxx", tmp_path)

    assert result == Path(tmp_path / "xyz.mp4")


def test_download_creates_output_dir(tmp_path):
    output_dir = tmp_path / "downloads"
    fake_info = {"requested_downloads": [{"filepath": str(output_dir / "a.mp4")}]}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        bilibili.download("https://www.bilibili.com/video/BVxxx", output_dir)

    assert output_dir.exists()
