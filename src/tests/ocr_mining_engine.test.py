from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from language import Language
from ocr_mining import engine


def _fake_line(text, width=0.8, center_y=0.5):
    return SimpleNamespace(text=text, bounding_box=SimpleNamespace(width=width, center_y=center_y))


def _fake_ocr_result(*lines):
    # Accepts either plain strings (wrapped with default bounding-box values) or
    # pre-built fake lines (via _fake_line, for tests that need custom width/position).
    wrapped = [line if hasattr(line, "bounding_box") else _fake_line(line) for line in lines]
    return SimpleNamespace(paragraphs=[SimpleNamespace(lines=wrapped)])


# _flatten_text
def test_flatten_text_joins_lines_across_paragraphs():
    result = SimpleNamespace(paragraphs=[
        SimpleNamespace(lines=[_fake_line("line one", center_y=0.4), _fake_line("line two", center_y=0.6)]),
        SimpleNamespace(lines=[_fake_line("line three", center_y=0.8)]),
    ])
    assert engine._flatten_text(result) == "line one\nline two\nline three"


def test_flatten_text_no_lines_returns_empty_string():
    result = _fake_ocr_result()
    assert engine._flatten_text(result) == ""


def test_flatten_text_drops_narrow_lines_relative_to_widest():
    # A wide, centered subtitle line alongside a narrow staff-credit-like column.
    result = _fake_ocr_result(_fake_line("dialogue subtitle line", width=0.8), _fake_line("原田", width=0.15))
    assert engine._flatten_text(result) == "dialogue subtitle line"


def test_flatten_text_keeps_comparably_wide_wrapped_lines_sorted_top_to_bottom():
    # A subtitle wrapped across two comparably-wide lines should be kept, in reading order.
    result = _fake_ocr_result(
        _fake_line("second wrapped line", width=0.75, center_y=0.7),
        _fake_line("first wrapped line", width=0.8, center_y=0.5),
    )
    assert engine._flatten_text(result) == "first wrapped line\nsecond wrapped line"


def test_flatten_text_skips_none_lines():
    result = _fake_ocr_result("hello", None)
    assert engine._flatten_text(result) == "hello"


# _build_impl - platform branching
def test_build_impl_uses_apple_vision_on_darwin():
    mock_apple_vision_cls = MagicMock(return_value=MagicMock(available=True))
    fake_module = MagicMock(AppleVision=mock_apple_vision_cls)

    with patch.object(engine.sys, "platform", "darwin"), \
         patch.dict("sys.modules", {"owocr.ocr": fake_module}):
        impl = engine._build_impl(Language.FRENCH)

    mock_apple_vision_cls.assert_called_once_with(language="fr-FR")
    assert impl is mock_apple_vision_cls.return_value


def test_build_impl_falls_back_to_easyocr_when_apple_vision_unavailable():
    mock_apple_vision_cls = MagicMock(return_value=MagicMock(available=False))
    mock_easyocr_cls = MagicMock(return_value=MagicMock(available=True))
    fake_module = MagicMock(AppleVision=mock_apple_vision_cls, EasyOCR=mock_easyocr_cls)

    with patch.object(engine.sys, "platform", "darwin"), \
         patch.dict("sys.modules", {"owocr.ocr": fake_module}):
        impl = engine._build_impl(Language.FRENCH)

    mock_easyocr_cls.assert_called_once_with(config={}, language="fr")
    assert impl is mock_easyocr_cls.return_value


def test_build_impl_uses_easyocr_on_non_darwin():
    mock_easyocr_cls = MagicMock(return_value=MagicMock(available=True))
    fake_module = MagicMock(EasyOCR=mock_easyocr_cls)

    with patch.object(engine.sys, "platform", "linux"), \
         patch.dict("sys.modules", {"owocr.ocr": fake_module}):
        impl = engine._build_impl(Language.ENGLISH_US)

    mock_easyocr_cls.assert_called_once_with(config={}, language="en")
    assert impl is mock_easyocr_cls.return_value


def test_build_impl_raises_when_no_engine_available():
    mock_easyocr_cls = MagicMock(return_value=MagicMock(available=False))
    fake_module = MagicMock(EasyOCR=mock_easyocr_cls)

    with patch.object(engine.sys, "platform", "linux"), \
         patch.dict("sys.modules", {"owocr.ocr": fake_module}):
        with pytest.raises(RuntimeError):
            engine._build_impl(Language.ENGLISH_US)


# OcrEngine.read_text
def test_read_text_returns_flattened_text_on_success():
    result = _fake_ocr_result("recognized text")
    fake_impl = MagicMock(return_value=(True, result))

    with patch.object(engine, "_build_impl", return_value=fake_impl):
        ocr_engine = engine.OcrEngine(Language.FRENCH)
        text = ocr_engine.read_text("frame_000000.jpg")

    assert text == "recognized text"
    # owocr's engines do `isinstance(img, Path)` internally - a plain str is rejected,
    # so read_text must convert it before calling the underlying engine.
    fake_impl.assert_called_once_with(Path("frame_000000.jpg"))


def test_read_text_returns_empty_string_on_failure():
    fake_impl = MagicMock(return_value=(False, "Unknown error!"))

    with patch.object(engine, "_build_impl", return_value=fake_impl):
        ocr_engine = engine.OcrEngine(Language.FRENCH)
        text = ocr_engine.read_text("frame_000000.jpg")

    assert text == ""
