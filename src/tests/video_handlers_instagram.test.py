from pathlib import Path
from unittest.mock import patch, MagicMock

import video_handlers.instagram as instagram


def test_domains():
    assert "instagram.com" in instagram.DOMAINS


def test_download_uses_requested_downloads_filepath(tmp_path):
    fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "abc123.mp4")}], "__real_download": True}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_cls:
        result = instagram.download("https://www.instagram.com/reel/xxx/", tmp_path)

    assert result == Path(tmp_path / "abc123.mp4")
    opts = mock_cls.call_args[0][0]
    assert opts["extractor_args"] == {"instagram": {"app_id": ["web"]}}


def test_download_passes_app_id(tmp_path):
    fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "id.mp4")}], "__real_download": True}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_cls:
        instagram.download("https://www.instagram.com/reel/xxx/", tmp_path, app_id="ios")

    opts = mock_cls.call_args[0][0]
    assert opts["extractor_args"] == {"instagram": {"app_id": ["ios"]}}


def test_download_falls_back_to_prepare_filename(tmp_path):
    fake_info = {"id": "xyz", "ext": "mp4", "__real_download": True}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(tmp_path / "xyz.mp4")
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = instagram.download("https://www.instagram.com/reel/xxx/", tmp_path)

    assert result == Path(tmp_path / "xyz.mp4")


def test_download_creates_output_dir(tmp_path):
    output_dir = tmp_path / "downloads"
    fake_info = {"requested_downloads": [{"filepath": str(output_dir / "a.mp4")}], "__real_download": True}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        instagram.download("https://www.instagram.com/reel/xxx/", output_dir)

    assert output_dir.exists()


def test_download_logs_skip_message_when_already_downloaded(tmp_path, capsys):
    fake_info = {
        "requested_downloads": [{"filepath": str(tmp_path / "abc123.mp4")}],
        "__real_download": False,
    }
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = instagram.download("https://www.instagram.com/reel/xxx/", tmp_path)

    assert result == Path(tmp_path / "abc123.mp4")
    assert "Skipped download" in capsys.readouterr().out
