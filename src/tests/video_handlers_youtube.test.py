from pathlib import Path
from unittest.mock import patch, MagicMock

import video_handlers.youtube as youtube
from language import Language


def test_domains():
    assert "youtube.com" in youtube.DOMAINS
    assert "youtu.be" in youtube.DOMAINS


def test_lang_codes_cover_all_languages():
    for lang in Language:
        assert lang in youtube.LANG_CODES
        assert youtube.LANG_CODES[lang]


def test_download_uses_requested_downloads_filepath(tmp_path):
    fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "abc123.mp4")}]}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_cls:
        result = youtube.download("https://www.youtube.com/watch?v=xxx", tmp_path)

    assert result == Path(tmp_path / "abc123.mp4")
    opts = mock_cls.call_args[0][0]
    assert "writesubtitles" not in opts


def test_download_requests_subtitles_for_language(tmp_path):
    fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "abc123.mp4")}]}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_cls:
        youtube.download(
            "https://www.youtube.com/watch?v=xxx", tmp_path, language=Language.MANDARIN_TW,
        )

    opts = mock_cls.call_args[0][0]
    assert opts["writesubtitles"] is True
    assert opts["writeautomaticsub"] is True
    assert opts["subtitleslangs"] == youtube.LANG_CODES[Language.MANDARIN_TW]
    assert opts["subtitlesformat"] == "srt"


def test_download_falls_back_to_prepare_filename(tmp_path):
    fake_info = {"id": "xyz", "ext": "mp4"}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.prepare_filename.return_value = str(tmp_path / "xyz.mp4")
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        result = youtube.download("https://youtu.be/xxx", tmp_path)

    assert result == Path(tmp_path / "xyz.mp4")


def test_download_creates_output_dir(tmp_path):
    output_dir = tmp_path / "downloads"
    fake_info = {"requested_downloads": [{"filepath": str(output_dir / "a.mp4")}]}
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = fake_info
    mock_ydl.__enter__.return_value = mock_ydl

    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
        youtube.download("https://www.youtube.com/shorts/xxx", output_dir)

    assert output_dir.exists()
