import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# Never read or write the user's real video game OCR selection (sources/game_ocr.json) from tests.
@pytest.fixture(autouse=True)
def _isolated_game_ocr_settings(tmp_path, monkeypatch):
    import game_ocr.settings
    path = tmp_path / "game_ocr.json"
    monkeypatch.setattr(game_ocr.settings, "GAME_OCR_SETTINGS", path)
    return path


# GUI tests (`make test-gui`): keep their windows hidden. Widgets work the same while withdrawn.
@pytest.fixture(autouse=True)
def _hidden_tk_windows(request, monkeypatch):
    if request.node.get_closest_marker("gui") is None:
        return
    import tkinter as tk
    for cls in (tk.Tk, tk.Toplevel):
        original_init = cls.__init__

        def hidden_init(self, *args, _original_init=original_init, **kwargs):
            _original_init(self, *args, **kwargs)
            self.withdraw()

        monkeypatch.setattr(cls, "__init__", hidden_init)
