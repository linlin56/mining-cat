from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from game_ocr import session as game_session
from game_ocr.capture import CaptureBackend, CaptureError
from game_ocr.session import ChangeDetector, GameOcrSession, crop_areas, crop_region, join_lines
from game_ocr.settings import GameOcrSettings
from language import Language


class FakeBackend(CaptureBackend):
    window_label = ""

    def __init__(self, frame: Image.Image):
        self.frame = frame
        self.closed = False
        self.restored_with = None

    def grab_frame(self):
        return self.frame

    def restore(self, state):
        self.restored_with = state

    @property
    def state(self):
        return {"token": "new"}

    def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self, text="你好世界"):
        self.text = text
        self.calls = []

    def read_text(self, image, drop_narrow_lines=True):
        self.calls.append((image.size, drop_narrow_lines))
        return self.text


def _settings(**overrides) -> GameOcrSettings:
    values = dict(
        backend="macos", backend_state={"id": 1, "owner": "Game"}, window_label="Game",
        screenshot_region=(0.0, 0.0, 1.0, 1.0), text_region=(0.0, 0.5, 1.0, 0.5),
    )
    values.update(overrides)
    return GameOcrSettings(**values)


def _session(frame=None, engine=None, language=Language.MANDARIN_TW, **kwargs) -> GameOcrSession:
    frame = frame or Image.new("RGB", (200, 100), "black")
    return GameOcrSession(FakeBackend(frame), _settings(), language, engine=engine or FakeEngine(), **kwargs)


# crops
def test_crop_region_none_is_whole_image():
    image = Image.new("RGB", (200, 100))
    assert crop_region(image, None).size == (200, 100)


def test_crop_areas_text_area_is_relative_to_screenshot_area():
    frame = Image.new("RGB", (400, 200))
    screenshot, text = crop_areas(frame, (0.5, 0.0, 0.5, 1.0), (0.0, 0.5, 1.0, 0.5))
    assert screenshot.size == (200, 200)
    assert text.size == (200, 100)


# join_lines
@pytest.mark.parametrize("language, expected", [
    (Language.MANDARIN_TW, "今天天氣很好我們去散步"),
    (Language.JAPANESE, "今天天氣很好我們去散步"),
    (Language.FRENCH, "今天天氣很好 我們去散步"),
    (Language.KOREAN, "今天天氣很好 我們去散步"),
])
def test_join_lines_depends_on_language(language, expected):
    assert join_lines("今天天氣很好\n 我們去散步 \n\n", language) == expected


# ChangeDetector
def _solid(color):
    return Image.new("RGB", (64, 32), color)


def test_change_detector_waits_for_a_stable_area_then_reads_once():
    detector = ChangeDetector()
    assert detector.should_read(_solid("white")) is False   # first poll
    assert detector.should_read(_solid("white")) is True    # stable -> read
    assert detector.should_read(_solid("white")) is False   # already read


def test_change_detector_skips_while_text_is_still_drawing():
    detector = ChangeDetector()
    detector.should_read(_solid("white"))
    detector.should_read(_solid("white"))
    assert detector.should_read(_solid("black")) is False   # changed: wait
    assert detector.should_read(_solid("gray")) is False    # still changing
    assert detector.should_read(_solid("gray")) is True     # settled on new text


# GameOcrSession.read
def test_read_keeps_every_line_and_joins_them():
    engine = FakeEngine("第一行\n第二行")
    assert _session(engine=engine).read(Image.new("RGB", (10, 10))) == "第一行第二行"
    assert engine.calls == [((10, 10), False)]


def test_read_can_keep_line_breaks():
    assert _session(engine=FakeEngine("第一行\n第二行"), join=False).read(Image.new("RGB", (10, 10))) == "第一行\n第二行"


def test_read_rejects_text_not_in_the_language_script():
    assert _session(engine=FakeEngine("|||")).read(Image.new("RGB", (10, 10))) == ""


def test_read_converts_chinese_script():
    text = _session(engine=FakeEngine("這是測試"), convert_target="s").read(Image.new("RGB", (10, 10)))
    assert text == "这是测试"


def test_convert_target_ignored_for_non_chinese_language():
    text = _session(engine=FakeEngine("Bonjour"), language=Language.FRENCH, convert_target="s").read(Image.new("RGB", (10, 10)))
    assert text == "Bonjour"


# GameOcrSession.capture
def test_capture_force_reads_immediately():
    result, reason = _session().capture(force=True)
    assert reason == ""
    assert result.text == "你好世界"
    assert result.screenshot.size == (200, 100)
    assert result.ms >= 0


def test_capture_auto_skips_until_area_is_stable():
    session = _session()
    assert session.capture() == (None, "text area unchanged")
    result, _ = session.capture()
    assert result.text == "你好世界"


def test_capture_skips_empty_text():
    assert _session(engine=FakeEngine("")).capture(force=True) == (None, "no text detected")


def test_capture_skips_repeated_text_until_forgotten():
    session = _session()
    session.capture(force=True)
    assert session.capture(force=True) == (None, "same text as the previous capture")
    session.forget_last_text()
    assert session.capture(force=True)[0] is not None


def test_capture_skips_long_near_duplicate_but_not_short_one():
    engine = FakeEngine("今天天氣很好我們一起去散步")
    session = _session(engine=engine)
    session.capture(force=True)
    engine.text = "今天天氣很好我們一起去散歩"   # one OCR jitter character on a long line
    assert session.capture(force=True)[1] == "same text as the previous capture"

    engine.text = "好的"
    session.capture(force=True)
    engine.text = "好吧"   # short lines: one character is a different line
    assert session.capture(force=True)[0].text == "好吧"


def test_session_builds_ocr_engine_for_language_by_default():
    with patch("ocr_mining.engine.OcrEngine") as engine_cls:
        GameOcrSession(FakeBackend(Image.new("RGB", (1, 1))), _settings(), Language.JAPANESE)
    engine_cls.assert_called_once_with(Language.JAPANESE)


# open_saved_window
def test_open_saved_window_restores_and_saves_new_state():
    backend = FakeBackend(Image.new("RGB", (1, 1)))
    settings = _settings()
    save = MagicMock()
    with patch.object(game_session.capture, "backend_info", return_value=MagicMock(id="macos")), \
         patch.object(game_session.capture, "create_backend", return_value=backend):
        assert game_session.open_saved_window(settings, save=save) is backend
    assert backend.restored_with == {"id": 1, "owner": "Game"}
    assert settings.backend_state == {"token": "new"}
    assert settings.window_label == "Game"  # FakeBackend has no label: the saved one is kept
    save.assert_called_once_with(settings)


def test_open_saved_window_updates_label_of_retitled_window():
    class RetitledBackend(FakeBackend):
        window_label = "Game - New title"

    backend = RetitledBackend(Image.new("RGB", (1, 1)))
    settings = _settings()
    with patch.object(game_session.capture, "backend_info", return_value=MagicMock(id="macos")), \
         patch.object(game_session.capture, "create_backend", return_value=backend):
        game_session.open_saved_window(settings, save=MagicMock())
    assert settings.window_label == "Game - New title"


def test_open_saved_window_rejects_settings_from_another_backend():
    with patch.object(game_session.capture, "backend_info", return_value=MagicMock(id="linux_wayland")):
        with pytest.raises(CaptureError, match="select the game window first"):
            game_session.open_saved_window(_settings(), save=MagicMock())


def test_open_saved_window_rejects_missing_window():
    with pytest.raises(CaptureError):
        game_session.open_saved_window(GameOcrSettings(), save=MagicMock())


def test_open_saved_window_closes_backend_when_restore_fails():
    backend = FakeBackend(Image.new("RGB", (1, 1)))
    backend.restore = MagicMock(side_effect=CaptureError("gone"))
    save = MagicMock()
    with patch.object(game_session.capture, "backend_info", return_value=MagicMock(id="macos")), \
         patch.object(game_session.capture, "create_backend", return_value=backend):
        with pytest.raises(CaptureError, match="gone"):
            game_session.open_saved_window(_settings(), save=save)
    assert backend.closed
    save.assert_not_called()
