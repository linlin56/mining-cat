import importlib.util
from unittest.mock import MagicMock, patch

import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

# Opens Tk windows: excluded from `make test`, run with `make test-gui`.
pytestmark = pytest.mark.gui

import tkinter as tk

from PIL import Image

from miningcat.interfaces.cli import area_picker


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    yield r
    r.destroy()


def _drag(dialog, start, end):
    event = lambda x, y: type("Event", (), {"x": x, "y": y})()
    dialog._on_drag_start(event(*start))
    dialog._on_drag_end(event(*end))


def test_region_dialog_shows_the_capture(root):
    dialog = area_picker.RegionDialog(root, Image.new("RGB", (1600, 900)), "Pick")
    root.update()
    assert dialog.title() == "Pick"
    assert dialog._canvas_size == (800, 450)
    dialog.destroy()


def test_region_dialog_ok_without_drag_returns_default_region(root):
    dialog = area_picker.RegionDialog(root, Image.new("RGB", (800, 450)), "Pick", default_region=(0, 0.5, 1, 0.5))
    dialog._on_ok()
    assert dialog._result == (0, 0.5, 1, 0.5)


def test_region_dialog_drag_returns_normalized_region(root):
    dialog = area_picker.RegionDialog(root, Image.new("RGB", (800, 450)), "Pick")
    _drag(dialog, (0, 225), (400, 450))
    dialog._on_ok()
    assert dialog._result == (0.0, 0.5, 0.5, 0.5)


def test_region_dialog_keeps_initial_region(root):
    dialog = area_picker.RegionDialog(root, Image.new("RGB", (800, 450)), "Pick", initial_region=(0.1, 0.1, 0.2, 0.2))
    dialog._on_ok()
    assert dialog._result == (0.1, 0.1, 0.2, 0.2)


def test_pick_region_returns_dialog_result():
    try:
        tk.Tk().destroy()
    except tk.TclError:
        pytest.skip("no display available")
    with patch.object(area_picker.RegionDialog, "show", return_value=(0, 0, 1, 1)) as show:
        assert area_picker.pick_region(Image.new("RGB", (80, 45)), "Pick") == (0, 0, 1, 1)
    show.assert_called_once()

