import pytest

import video_handlers
import video_handlers.instagram as instagram


def test_get_handler_instagram():
    assert video_handlers.get_handler("https://www.instagram.com/reel/xxx/") is instagram


def test_get_handler_instagram_without_www():
    assert video_handlers.get_handler("https://instagram.com/reel/xxx/") is instagram


def test_get_handler_unknown_host_raises():
    with pytest.raises(ValueError):
        video_handlers.get_handler("https://www.youtube.com/watch?v=xxx")
