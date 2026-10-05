import importlib.util
import time
from unittest.mock import MagicMock, patch

import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

# Opens Tk windows: excluded from `make test`, run with `make test-gui`.
pytestmark = pytest.mark.gui

import tkinter as tk
from PIL import Image

from game_ocr.capture import CaptureBackend, CaptureError, WindowInfo
from game_ocr.settings import GameOcrSettings
from gui_components import game_panel as game_panel_module
from gui_components.game_panel import GamePanel
from gui_config import COLORS as _COLORS

MACOS = MagicMock(id="macos", label="macOS")


class FakeBackend(CaptureBackend):
    def __init__(self, system_picker=False):
        self.has_system_picker = system_picker
        self.selected = None
        self.closed = False

    def list_windows(self):
        return [WindowInfo(3, "Ryujinx", "Zelda")]

    def select_window(self, window=None):
        self.selected = window or WindowInfo(0, "portal")

    @property
    def state(self):
        return {"id": self.selected.id} if self.selected else {}

    @property
    def window_label(self):
        return self.selected.label if self.selected else ""

    def grab_frame(self):
        return Image.new("RGB", (200, 100))

    def close(self):
        self.closed = True


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    yield r
    r.destroy()


def _ready_settings():
    return GameOcrSettings(backend="macos", backend_state={"id": 3}, window_label="Ryujinx - Zelda",
                           screenshot_region=(0, 0, 1, 1), text_region=(0, 0.5, 1, 0.5))


def _panel(root, backend_info=MACOS):
    with patch.object(game_panel_module.capture, "backend_info", return_value=backend_info):
        return GamePanel(root, _COLORS)


def _wait_idle(root, panel, timeout=5):
    deadline = time.time() + timeout
    while panel._busy and time.time() < deadline:
        root.update()
        time.sleep(0.01)
    root.update()


def test_nothing_selected(root):
    panel = _panel(root)
    assert panel.is_supported and not panel.is_ready
    assert str(panel._window_btn.cget("state")) == "normal"
    assert str(panel._screenshot_btn.cget("state")) == "disabled"
    assert str(panel._text_btn.cget("state")) == "disabled"
    assert panel._window_lbl.cget("text") == "No window selected"


def test_unsupported_os_disables_everything(root):
    panel = _panel(root, backend_info=None)
    assert not panel.is_supported
    assert str(panel._window_btn.cget("state")) == "disabled"


def test_loads_saved_selection(root):
    _ready_settings().save()
    panel = _panel(root)
    assert panel.is_ready
    assert panel._window_lbl.cget("text") == "Ryujinx - Zelda"
    assert panel._text_lbl.cget("text") == "Selected"
    assert str(panel._text_btn.cget("state")) == "normal"


def test_ignores_selection_saved_by_another_backend(root):
    _ready_settings().save()
    panel = _panel(root, backend_info=MagicMock(id="linux_wayland", label="Linux"))
    assert not panel.is_ready


def test_capture_key_is_the_default_trigger(root):
    panel = _panel(root)
    assert panel.hotkey == "F9"
    assert panel.continuous is False
    assert str(panel._hotkey_combo.cget("state")) == "readonly"


def test_continuous_capture_greys_out_the_key_and_is_remembered(root):
    panel = _panel(root)
    panel._hotkey_var.set("F7")
    panel._continuous_var.set(True)
    panel._on_trigger_change()
    assert str(panel._hotkey_combo.cget("state")) == "disabled"
    saved = GameOcrSettings.load()
    assert (saved.hotkey, saved.continuous) == ("F7", True)

    reopened = _panel(root)
    assert reopened.hotkey == "F7" and reopened.continuous is True


def test_unknown_saved_key_falls_back_to_default(root):
    GameOcrSettings(hotkey="F42").save()
    assert _panel(root).hotkey == "F9"


def test_locked_disables_selection_and_reloads_on_unlock(root):
    panel = _panel(root)
    panel.set_locked(True)
    assert str(panel._window_btn.cget("state")) == "disabled"
    assert str(panel._continuous_check.cget("state")) == "disabled"
    assert str(panel._hotkey_combo.cget("state")) == "disabled"
    _ready_settings().save()  # e.g. the subprocess saved a new restore token
    panel.set_locked(False)
    assert panel.is_ready


def test_on_change_is_called_on_refresh(root):
    panel = _panel(root)
    panel.on_change = MagicMock()
    panel._refresh()
    panel.on_change.assert_called_once()


def test_select_window_from_list(root):
    panel = _panel(root)
    backend = FakeBackend()
    window = WindowInfo(3, "Ryujinx", "Zelda")
    with patch.object(game_panel_module.capture, "create_backend", return_value=backend), \
         patch("gui_components.game_dialogs.WindowPickerDialog") as dialog:
        dialog.return_value.show.return_value = window
        panel._select_window()
    assert backend.selected == window and backend.closed
    assert GameOcrSettings.load().window_label == "Ryujinx - Zelda"
    assert str(panel._screenshot_btn.cget("state")) == "normal"


def test_select_window_cancelled_keeps_settings(root):
    panel = _panel(root)
    with patch.object(game_panel_module.capture, "create_backend", return_value=FakeBackend()), \
         patch("gui_components.game_dialogs.WindowPickerDialog") as dialog:
        dialog.return_value.show.return_value = None
        panel._select_window()
    assert not GameOcrSettings.load().has_window


def test_select_window_without_permission_shows_error(root):
    panel = _panel(root)
    backend = FakeBackend()
    backend.list_windows = MagicMock(side_effect=CaptureError("needs Screen Recording permission"))
    with patch.object(game_panel_module.capture, "create_backend", return_value=backend), \
         patch.object(game_panel_module.messagebox, "showerror") as showerror, \
         patch("gui_components.game_dialogs.WindowPickerDialog") as dialog:
        panel._select_window()
    showerror.assert_called_once()
    dialog.assert_not_called()
    assert backend.closed


def test_select_window_with_system_picker_runs_in_background(root):
    panel = _panel(root, backend_info=MagicMock(id="linux_wayland", label="Linux"))
    backend = FakeBackend(system_picker=True)
    with patch.object(game_panel_module.capture, "create_backend", return_value=backend):
        panel._select_window()
        _wait_idle(root, panel)
    saved = GameOcrSettings.load()
    assert saved.backend == "linux_wayland" and saved.window_label == "portal"
    assert backend.closed


def test_create_backend_failure_shows_error(root):
    panel = _panel(root)
    with patch.object(game_panel_module.capture, "create_backend", side_effect=CaptureError("pyobjc missing")), \
         patch.object(game_panel_module.messagebox, "showerror") as showerror:
        panel._select_window()
    showerror.assert_called_once_with("Screen capture", "pyobjc missing")


def test_select_areas_grab_a_frame_then_save_regions(root):
    _ready_settings().save()
    panel = _panel(root)
    with patch("game_ocr.session.open_saved_window", return_value=FakeBackend()), \
         patch("gui_components.game_dialogs.WindowRegionDialog") as dialog:
        dialog.return_value.show.return_value = (0.5, 0.0, 0.5, 1.0)
        panel._select_screenshot_area()
        _wait_idle(root, panel)
        assert GameOcrSettings.load().screenshot_region == (0.5, 0.0, 0.5, 1.0)
        assert not panel.is_ready  # new screenshot area: text area must be picked again

        dialog.return_value.show.return_value = (0.0, 0.6, 1.0, 0.4)
        panel._select_text_area()
        _wait_idle(root, panel)
    # the text area dialog is shown on the screenshot area only, pre-selected on all of it
    assert dialog.call_args[0][1].size == (100, 100)
    assert "default_region" not in dialog.call_args[1]
    assert GameOcrSettings.load().text_region == (0.0, 0.6, 1.0, 0.4)
    assert panel.is_ready


def test_select_area_cancelled_keeps_regions(root):
    _ready_settings().save()
    panel = _panel(root)
    with patch("game_ocr.session.open_saved_window", return_value=FakeBackend()), \
         patch("gui_components.game_dialogs.WindowRegionDialog") as dialog:
        dialog.return_value.show.return_value = None
        panel._select_screenshot_area()
        _wait_idle(root, panel)
        panel._select_text_area()
        _wait_idle(root, panel)
    assert GameOcrSettings.load() == _ready_settings()


def test_select_area_capture_error_shows_error(root):
    _ready_settings().save()
    panel = _panel(root)
    with patch("game_ocr.session.open_saved_window", side_effect=CaptureError("window gone")), \
         patch.object(game_panel_module.messagebox, "showerror") as showerror:
        panel._select_text_area()
        _wait_idle(root, panel)
    showerror.assert_called_once_with("Screen capture", "window gone")
    assert str(panel._text_btn.cget("state")) == "normal"
