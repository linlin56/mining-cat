import importlib.util
from unittest.mock import MagicMock, patch

import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

# Opens Tk windows: excluded from `make test`, run with `make test-gui`.
pytestmark = pytest.mark.gui

import tkinter as tk
from PIL import Image

from game_ocr.capture import CaptureError, WindowInfo
from gui_components import game_dialogs

WINDOWS = [WindowInfo(1, "Steam", "Game A"), WindowInfo(2, "Ryujinx")]


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


# WindowRegionDialog
def test_region_dialog_shows_the_capture_without_carousel(root):
    dialog = game_dialogs.WindowRegionDialog(root, Image.new("RGB", (1600, 900)), "Pick")
    root.update()
    assert dialog.title() == "Pick"
    assert dialog._canvas_size == (800, 450)
    assert not dialog._nav_row.winfo_ismapped()
    dialog.destroy()


def test_region_dialog_ok_without_drag_returns_default_region(root):
    dialog = game_dialogs.WindowRegionDialog(root, Image.new("RGB", (800, 450)), "Pick", default_region=(0, 0.5, 1, 0.5))
    dialog._on_ok()
    assert dialog._result == (0, 0.5, 1, 0.5)


def test_region_dialog_drag_returns_normalized_region(root):
    dialog = game_dialogs.WindowRegionDialog(root, Image.new("RGB", (800, 450)), "Pick")
    _drag(dialog, (0, 225), (400, 450))
    dialog._on_ok()
    assert dialog._result == (0.0, 0.5, 0.5, 0.5)


def test_region_dialog_keeps_initial_region(root):
    dialog = game_dialogs.WindowRegionDialog(root, Image.new("RGB", (800, 450)), "Pick", initial_region=(0.1, 0.1, 0.2, 0.2))
    dialog._on_ok()
    assert dialog._result == (0.1, 0.1, 0.2, 0.2)


def test_pick_region_standalone_returns_dialog_result():
    try:
        tk.Tk().destroy()
    except tk.TclError:
        pytest.skip("no display available")
    with patch.object(game_dialogs.WindowRegionDialog, "show", return_value=(0, 0, 1, 1)) as show:
        assert game_dialogs.pick_region_standalone(Image.new("RGB", (80, 45)), "Pick") == (0, 0, 1, 1)
    show.assert_called_once()


# WindowPickerDialog
def test_picker_lists_windows_and_returns_selection(root):
    dialog = game_dialogs.WindowPickerDialog(root, lambda: WINDOWS, MagicMock())
    assert dialog._listbox.get(0, "end") == ("Steam - Game A", "Ryujinx")
    dialog._listbox.selection_set(1)
    dialog._on_ok()
    assert dialog._result == WINDOWS[1]


def test_picker_ok_without_selection_does_nothing(root):
    dialog = game_dialogs.WindowPickerDialog(root, lambda: WINDOWS, MagicMock())
    dialog._on_ok()
    assert dialog.winfo_exists()
    dialog._on_cancel()
    assert dialog._result is None


def test_picker_refresh_error_is_reported_and_keeps_previous_list(root):
    calls = iter([WINDOWS, CaptureError("permission")])

    def list_windows():
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    on_error = MagicMock()
    dialog = game_dialogs.WindowPickerDialog(root, list_windows, on_error)
    dialog._refresh()
    on_error.assert_called_once()
    assert dialog._listbox.size() == 2
    dialog.destroy()
