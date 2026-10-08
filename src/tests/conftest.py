import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# Never read or write the user's files (sources/, output/, library/ and its database): everything goes to a
# temporary folder. Every page reads the language studied from the database.
@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    from miningcat.config.paths import paths
    from miningcat.infrastructure.persistence.database import database
    monkeypatch.setattr(paths, "root", tmp_path)
    database.reset_cache()
    yield
    database.reset_cache()


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
