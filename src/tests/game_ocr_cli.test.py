import argparse
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from game_ocr import cli
from game_ocr.capture import CaptureBackend, CaptureError, WindowInfo
from game_ocr.settings import GameOcrSettings
from language import Language

WINDOWS = [WindowInfo(1, "Steam", "Game A"), WindowInfo(2, "Ryujinx", "Zelda")]
MACOS = MagicMock(id="macos", label="macOS")


class FakeBackend(CaptureBackend):
    def __init__(self, system_picker=False):
        self.has_system_picker = system_picker
        self.selected = "none"
        self.closed = False

    def list_windows(self):
        return WINDOWS

    def select_window(self, window=None):
        self.selected = window

    @property
    def state(self):
        return {"id": 2}

    @property
    def window_label(self):
        return "Ryujinx - Zelda"

    def grab_frame(self):
        return Image.new("RGB", (200, 100))

    def close(self):
        self.closed = True


# choose_window
def test_choose_window_by_query_is_case_insensitive():
    assert cli.choose_window(WINDOWS, "zelda") == WINDOWS[1]


def test_choose_window_query_without_match_lists_windows():
    with pytest.raises(CaptureError, match="Steam - Game A"):
        cli.choose_window(WINDOWS, "mario")


def test_choose_window_no_windows_raises():
    with pytest.raises(CaptureError, match="No capturable window"):
        cli.choose_window([], None)


def test_choose_window_asks_until_valid(capsys):
    answers = iter(["abc", "9", "2"])
    assert cli.choose_window(WINDOWS, None, ask=lambda _prompt: next(answers)) == WINDOWS[1]
    out = capsys.readouterr().out
    assert " 1. Steam - Game A" in out
    assert out.count("Invalid choice") == 2


# select_window
def test_select_window_from_list_saves_settings():
    backend, settings = FakeBackend(), GameOcrSettings()
    with patch.object(cli.capture, "backend_info", return_value=MACOS):
        cli.select_window(backend, settings, "zelda")
    assert backend.selected == WINDOWS[1]
    assert GameOcrSettings.load() == GameOcrSettings(backend="macos", backend_state={"id": 2}, window_label="Ryujinx - Zelda")


def test_select_window_with_system_picker_does_not_list(capsys):
    backend = FakeBackend(system_picker=True)
    with patch.object(cli.capture, "backend_info", return_value=MagicMock(id="linux_wayland")):
        cli.select_window(backend, GameOcrSettings())
    assert backend.selected is None
    assert "system dialog" in capsys.readouterr().out


# select_areas
def test_select_areas_saves_both_regions():
    settings = GameOcrSettings(backend="macos", backend_state={"id": 2})
    regions = iter([(0.0, 0.0, 0.5, 1.0), (0.0, 0.5, 1.0, 0.5)])
    with patch("gui_components.game_dialogs.pick_region_standalone", side_effect=lambda image, *_a, **_k: next(regions)) as pick:
        assert cli.select_areas(FakeBackend(), settings) is True
    assert pick.call_args_list[1][0][0].size == (100, 100)  # text area picked on the screenshot area
    saved = GameOcrSettings.load()
    assert saved.screenshot_region == (0.0, 0.0, 0.5, 1.0)
    assert saved.text_region == (0.0, 0.5, 1.0, 0.5)


def test_select_areas_cancelled_on_screenshot_area():
    with patch("gui_components.game_dialogs.pick_region_standalone", return_value=None):
        assert cli.select_areas(FakeBackend(), GameOcrSettings()) is False


def test_select_areas_cancelled_on_text_area_keeps_screenshot_area():
    regions = iter([(0.0, 0.0, 1.0, 1.0), None])
    with patch("gui_components.game_dialogs.pick_region_standalone", side_effect=lambda *_a, **_k: next(regions)):
        assert cli.select_areas(FakeBackend(), GameOcrSettings()) is False
    assert GameOcrSettings.load().screenshot_region == (0.0, 0.0, 1.0, 1.0)


# setup
def test_setup_selects_window_then_areas_and_closes_backend():
    backend = FakeBackend()
    with patch.object(cli.capture, "backend_info", return_value=MACOS), \
         patch.object(cli.capture, "create_backend", return_value=backend), \
         patch.object(cli, "select_areas", return_value=True) as select_areas:
        cli.setup(window_query="zelda")
    assert backend.selected == WINDOWS[1]
    select_areas.assert_called_once()
    assert backend.closed


def test_setup_areas_only_reopens_saved_window():
    backend = FakeBackend()
    with patch.object(cli.capture, "backend_info", return_value=MACOS), \
         patch("game_ocr.session.open_saved_window", return_value=backend) as open_saved, \
         patch.object(cli, "select_areas", return_value=True):
        cli.setup(areas_only=True)
    open_saved.assert_called_once()
    assert backend.selected == "none"


def test_setup_cancelled_exits():
    with patch.object(cli.capture, "backend_info", return_value=MACOS), \
         patch.object(cli.capture, "create_backend", return_value=FakeBackend()), \
         patch.object(cli, "select_areas", return_value=False):
        with pytest.raises(SystemExit, match="cancelled"):
            cli.setup(window_query="zelda")


# serve
def test_serve_without_selection_exits():
    with pytest.raises(SystemExit, match="game setup"):
        cli.serve(Language.JAPANESE)


def test_serve_wires_session_and_server_then_closes_backend():
    GameOcrSettings(backend="macos", backend_state={"id": 2}, window_label="Zelda", text_region=(0, 0.5, 1, 0.5)).save()
    backend = FakeBackend()
    with patch("game_ocr.session.open_saved_window", return_value=backend), \
         patch("game_ocr.session.GameOcrSession") as session_cls, \
         patch("game_ocr.server.create_app") as create_app, \
         patch("game_ocr.server.run") as run:
        cli.serve(Language.MANDARIN_TW, convert_target="s", port=7002, auto=True, interval=1.5, join=False, open_browser=False)
    _backend, _settings, language = session_cls.call_args[0]
    assert language is Language.MANDARIN_TW
    assert session_cls.call_args[1] == {"convert_target": "s", "join": False}
    create_app.assert_called_once_with(
        session_cls.return_value, Language.MANDARIN_TW, auto=True, interval=1.5, hotkey=None, port=7002,
    )
    run.assert_called_once_with(create_app.return_value, port=7002, open_browser=False)
    assert backend.closed


# main
def _args(**overrides):
    values = dict(game_command="serve", language="japanese", convert_to=None, port=None, interval=None,
                  continuous=False, hotkey="F9", keep_line_breaks=False, no_browser=False, window=None, areas_only=False)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_main_dispatches_serve_options():
    with patch.object(cli, "serve") as serve:
        cli.main(_args(continuous=True, hotkey="F2", keep_line_breaks=True, no_browser=True, port=7003))
    serve.assert_called_once_with(
        language=Language.JAPANESE, convert_target=None, port=7003, auto=True, hotkey="F2", interval=None,
        join=False, open_browser=False,
    )


def test_main_dispatches_setup():
    with patch.object(cli, "setup") as setup:
        cli.main(_args(game_command="setup", window="zelda", areas_only=True))
    setup.assert_called_once_with(window_query="zelda", areas_only=True)


def test_main_turns_capture_errors_into_exit_message():
    with patch.object(cli, "setup", side_effect=CaptureError("no permission")):
        with pytest.raises(SystemExit, match="Error: no permission"):
            cli.main(_args(game_command="setup"))


def _serve_with_patches(**kwargs):
    GameOcrSettings(backend="macos", backend_state={"id": 2}, window_label="Zelda", text_region=(0, 0.5, 1, 0.5)).save()
    with patch("game_ocr.session.open_saved_window", return_value=FakeBackend()), \
         patch("game_ocr.session.GameOcrSession"), \
         patch("game_ocr.server.create_app") as create_app, \
         patch("game_ocr.server.run"):
        cli.serve(Language.JAPANESE, open_browser=False, **kwargs)
    return create_app.call_args[1]


def test_serve_uses_the_capture_key_by_default():
    fake_key = MagicMock()
    with patch("game_ocr.hotkey.create_hotkey", return_value=fake_key) as create_hotkey:
        kwargs = _serve_with_patches(hotkey="F9")
    create_hotkey.assert_called_once_with("F9")
    assert kwargs["hotkey"] is fake_key and kwargs["auto"] is False


def test_serve_without_usable_key_still_serves(capsys):
    from game_ocr.hotkey import HotkeyError
    with patch("game_ocr.hotkey.create_hotkey", side_effect=HotkeyError("not on this OS")):
        kwargs = _serve_with_patches(hotkey="F9")
    assert kwargs["hotkey"] is None
    assert "not on this OS" in capsys.readouterr().out


def test_select_areas_text_area_defaults_to_whole_screenshot_area():
    regions = iter([(0.0, 0.0, 1.0, 1.0), (0.0, 0.5, 1.0, 0.5)])
    with patch("gui_components.game_dialogs.pick_region_standalone", side_effect=lambda *_a, **_k: next(regions)) as pick:
        cli.select_areas(FakeBackend(), GameOcrSettings())
    assert "default_region" not in pick.call_args_list[1][1]
