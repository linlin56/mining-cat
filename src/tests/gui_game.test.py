# The "Video game / Screen share" screen of the main window.
import importlib.util
from unittest.mock import MagicMock, patch

import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

# Opens Tk windows: excluded from `make test`, run with `make test-gui`.
pytestmark = pytest.mark.gui

import tkinter as tk

from game_ocr.settings import GameOcrSettings
from language import Language


@pytest.fixture
def app():
    import gui
    try:
        application = gui.App()
    except tk.TclError:
        pytest.skip("no display available")
    application.withdraw()
    yield application
    application.destroy()


def _make_ready(app):
    app._game_panel._settings = GameOcrSettings(
        backend="macos", backend_state={"id": 1}, window_label="Game", text_region=(0, 0.5, 1, 0.5),
    )
    app._game_panel._refresh()


def test_source_switches_to_game_screen(app):
    import gui
    app._source_var.set(gui.SOURCE_GAME)
    app._on_source_change()
    assert app._game_screen.winfo_manager() == "pack"
    assert app._video_screen.winfo_manager() == ""
    assert app._audiobook_screen.winfo_manager() == ""

    app._source_var.set(gui.SOURCE_AUDIOBOOK)
    app._on_source_change()
    assert app._audiobook_screen.winfo_manager() == "pack"
    assert app._game_screen.winfo_manager() == ""


def test_start_disabled_until_selection_is_ready(app):
    assert str(app._game_start_btn.cget("state")) == "disabled"
    _make_ready(app)
    assert str(app._game_start_btn.cget("state")) == "normal"
    assert str(app._game_page_btn.cget("state")) == "disabled"


def test_toggle_game_without_selection_warns(app):
    with patch("gui.messagebox.showwarning") as showwarning, patch("gui.pipeline.start_game_server") as start:
        app._toggle_game()
    showwarning.assert_called_once()
    start.assert_not_called()


def test_start_then_stop_then_exit(app):
    _make_ready(app)
    app._lang_var.set(Language.JAPANESE.value.label)
    proc = MagicMock()
    with patch("gui.pipeline.start_game_server", return_value=proc) as start:
        app._toggle_game()
    kwargs = start.call_args[1]
    assert kwargs["lang"] is Language.JAPANESE
    assert kwargs["continuous"] is False
    assert kwargs["hotkey"] == "F9"
    assert app._game_start_btn.cget("text") == "Stop"
    assert str(app._source_combo.cget("state")) == "disabled"
    assert str(app._game_panel._window_btn.cget("state")) == "disabled"
    assert str(app._game_page_btn.cget("state")) == "normal"

    with patch("gui.pipeline.stop_game_server") as stop:
        app._toggle_game()
        for _ in range(50):
            if stop.called:
                break
            app.update()
    stop.assert_called_once_with(proc)

    # the output pump reports the exit
    GameOcrSettings(backend="macos", backend_state={"id": 1}, window_label="Game", text_region=(0, 0.5, 1, 0.5)).save()
    kwargs["on_exit"](0)
    assert app._game_proc is None
    assert app._game_start_btn.cget("text") == "Start"
    assert str(app._source_combo.cget("state")) == "readonly"
    assert str(app._game_panel._window_btn.cget("state")) == "normal"


def test_open_page_opens_browser(app):
    with patch("gui.webbrowser.open") as open_browser:
        app._open_game_page()
    open_browser.assert_called_once_with("http://127.0.0.1:6677/")


def test_closing_the_window_stops_the_capture():
    import gui
    try:
        application = gui.App()
    except tk.TclError:
        pytest.skip("no display available")
    proc = MagicMock()
    application._game_proc = proc
    with patch("gui.pipeline.stop_game_server") as stop:
        application._on_close()
    stop.assert_called_once_with(proc)
