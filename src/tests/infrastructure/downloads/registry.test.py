import pytest

from miningcat.infrastructure.downloads import registry as video_handlers
from miningcat.infrastructure.downloads.registry import video_handlers as registry

bilibili = registry.for_website("Bilibili")
instagram = registry.for_website("Instagram")
youtube = registry.for_website("YouTube")


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


def test_websites_and_hints_come_from_the_handlers():
    assert registry.websites == ["Instagram", "YouTube", "Bilibili"]
    assert registry.url_hints["Bilibili"].startswith("https://www.bilibili.com/")
    assert registry.for_website("TikTok") is None
