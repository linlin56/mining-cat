import subprocess
import time
from unittest.mock import MagicMock, patch

from miningcat.application.game_ocr.capture_process import GameCaptureProcess
from miningcat.domain.languages import Language
from miningcat.infrastructure.system import processes


def _start(**overrides):
    fake_proc = MagicMock()
    fake_proc.stdout = iter(["Page: http://127.0.0.1:6677/\n"])
    fake_proc.wait.return_value = 0
    kwargs = dict(language=Language.JAPANESE, convert_target=None, continuous=False, hotkey="F9")
    kwargs.update(overrides)
    process = GameCaptureProcess(**kwargs)
    on_line, on_exit = MagicMock(), MagicMock()
    with patch.object(processes, "start", return_value=fake_proc) as start:
        process.start(on_line, on_exit)
        # the output pump runs in a thread: wait for it to report the exit
        for _ in range(100):
            if on_exit.called:
                break
            time.sleep(0.01)
    return start.call_args[0][0], on_line, on_exit


def test_runs_game_serve_and_pumps_output():
    args, on_line, on_exit = _start()
    assert args[-6:] == ["game", "serve", "--language", "japanese", "--hotkey", "F9"]
    on_line.assert_called_once_with("Page: http://127.0.0.1:6677/\n")
    on_exit.assert_called_once_with(0)


def test_passes_convert_and_continuous_without_key():
    args, _, _ = _start(language=Language.MANDARIN_TW, convert_target="s", continuous=True)
    assert args[args.index("--convert-to") + 1] == "s"
    assert "--continuous" in args
    assert "--hotkey" not in args


def test_without_its_own_page():
    assert "--no-browser" in _start(open_browser=False)[0]
    assert "--no-browser" not in _start()[0]


def test_stop_terminates_running_process():
    proc = MagicMock(**{"poll.return_value": None})
    processes.stop(proc)
    proc.terminate.assert_called_once()
    proc.kill.assert_not_called()


def test_stop_kills_when_terminate_times_out():
    proc = MagicMock(**{"poll.return_value": None})
    proc.wait.side_effect = subprocess.TimeoutExpired("game", 1)
    processes.stop(proc, timeout=0.01)
    proc.kill.assert_called_once()


def test_stop_ignores_finished_process():
    proc = MagicMock(**{"poll.return_value": 0})
    processes.stop(proc)
    proc.terminate.assert_not_called()
