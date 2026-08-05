import pytest

import video_handlers
import video_handlers.bilibili as bilibili
import video_handlers.instagram as instagram
import video_handlers.youtube as youtube


def test_get_handler_bilibili():
    assert video_handlers.get_handler("https://www.bilibili.com/video/BVxxx") is bilibili


def test_get_handler_bilibili_without_www():
    assert video_handlers.get_handler("https://bilibili.com/video/BVxxx") is bilibili


def test_get_handler_instagram():
    assert video_handlers.get_handler("https://www.instagram.com/reel/xxx/") is instagram


def test_get_handler_instagram_without_www():
    assert video_handlers.get_handler("https://instagram.com/reel/xxx/") is instagram


def test_get_handler_youtube():
    assert video_handlers.get_handler("https://www.youtube.com/watch?v=xxx") is youtube


def test_get_handler_youtube_shorts():
    assert video_handlers.get_handler("https://www.youtube.com/shorts/xxx") is youtube


def test_get_handler_youtube_short_domain():
    assert video_handlers.get_handler("https://youtu.be/xxx") is youtube


def test_get_handler_youtube_mobile():
    assert video_handlers.get_handler("https://m.youtube.com/watch?v=xxx") is youtube


def test_get_handler_unknown_host_raises():
    with pytest.raises(ValueError):
        video_handlers.get_handler("https://www.tiktok.com/@user/video/xxx")
