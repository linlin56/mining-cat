import importlib.util
import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

import tkinter as tk

from gui_components.video_panel import VideoPanel
from gui_config import COLORS as _COLORS


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    yield r
    r.destroy()


@pytest.fixture
def panel(root):
    return VideoPanel(root, _COLORS)


def test_url_starts_as_placeholder(panel):
    assert panel.url == ""
    assert panel._url_placeholder_active is True


def test_focus_in_clears_placeholder(panel):
    panel._on_url_focus_in()
    assert panel._url_placeholder_active is False
    assert panel._url_var.get() == ""


def test_focus_out_restores_placeholder_when_empty(panel):
    panel._on_url_focus_in()
    panel._on_url_focus_out()
    assert panel._url_placeholder_active is True


def test_focus_out_keeps_typed_url(panel):
    panel._on_url_focus_in()
    panel._url_var.set("https://www.youtube.com/watch?v=xxx")
    panel._on_url_focus_out()
    assert panel._url_placeholder_active is False
    assert panel.url == "https://www.youtube.com/watch?v=xxx"


def test_website_change_refreshes_placeholder_text(panel):
    panel._website_var.set("Bilibili")
    panel._on_website_change()
    assert "bilibili.com" in panel._url_var.get()


def test_website_change_does_not_override_typed_url(panel):
    panel._on_url_focus_in()
    panel._url_var.set("https://www.youtube.com/watch?v=xxx")
    panel._website_var.set("Bilibili")
    panel._on_website_change()
    assert panel._url_var.get() == "https://www.youtube.com/watch?v=xxx"


def test_validate_url_empty_is_valid(panel):
    assert panel.validate_url() is None


def test_validate_url_matching_website_is_valid(panel):
    panel._website_var.set("YouTube")
    panel._on_url_focus_in()
    panel._url_var.set("https://www.youtube.com/watch?v=xxx")
    assert panel.validate_url() is None


def test_validate_url_mismatched_website_errors(panel):
    panel._website_var.set("Bilibili")
    panel._on_url_focus_in()
    panel._url_var.set("https://www.youtube.com/watch?v=xxx")
    error = panel.validate_url()
    assert error is not None
    assert "Bilibili" in error


def test_validate_url_unsupported_platform_errors(panel):
    panel._on_url_focus_in()
    panel._url_var.set("https://www.tiktok.com/@user/video/xxx")
    error = panel.validate_url()
    assert error is not None
