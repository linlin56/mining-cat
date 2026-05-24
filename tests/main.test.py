import sys
import pytest
from unittest.mock import patch
import main


def test_main_dispatches_audio():
    with patch.object(sys, "argv", ["main.py", "audio"]):
        with patch("main.cmd_audio") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_epub():
    with patch.object(sys, "argv", ["main.py", "epub"]):
        with patch("main.cmd_epub") as mock:
            main.main()
    mock.assert_called_once()


def test_main_no_command_exits():
    with patch.object(sys, "argv", ["main.py"]):
        with pytest.raises(SystemExit):
            main.main()
