import importlib.util
from unittest.mock import patch, MagicMock
import pytest

if importlib.util.find_spec("_tkinter") is None:
    pytest.skip("tkinter not available", allow_module_level=True)

import gui


def test_main_creates_app_and_calls_mainloop():
    mock_app = MagicMock()
    with patch.object(gui, "App", return_value=mock_app):
        gui.main()
    mock_app.mainloop.assert_called_once()
