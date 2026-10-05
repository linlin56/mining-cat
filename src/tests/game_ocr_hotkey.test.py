import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from game_ocr import hotkey
from game_ocr.hotkey import GnomeHotkey, HotkeyError, MacOSHotkey

URL = "http://127.0.0.1:6677/capture"
PATH = hotkey._GNOME_BINDING_PATH
SCHEMA = hotkey._GNOME_BINDING_SCHEMA


def test_supported_keys_and_default():
    assert hotkey.HOTKEYS == tuple(f"F{i}" for i in range(1, 13))
    assert hotkey.DEFAULT_HOTKEY == "F9"


def test_unsupported_key_raises():
    with pytest.raises(HotkeyError, match="Unsupported capture key"):
        hotkey.Hotkey("A")


def test_base_hotkey_is_abstract():
    with pytest.raises(NotImplementedError):
        hotkey.Hotkey("F9").start(lambda: None, URL)
    hotkey.Hotkey("F9").stop()


def test_create_hotkey_switch():
    assert isinstance(hotkey.create_hotkey("F9", "linux"), GnomeHotkey)
    with patch.object(hotkey, "MacOSHotkey") as macos_cls:
        assert hotkey.create_hotkey("F9", "darwin") is macos_cls.return_value
    with pytest.raises(HotkeyError, match="win32"):
        hotkey.create_hotkey("F9", "win32")


def test_create_hotkey_defaults_to_current_platform():
    with patch.object(hotkey.sys, "platform", "linux"):
        assert isinstance(hotkey.create_hotkey("F9"), GnomeHotkey)


@pytest.mark.parametrize("value, expected", [
    ("@as []\n", []),
    ("['/a/', '/b/']\n", ["/a/", "/b/"]),
])
def test_parse_gsettings_list(value, expected):
    assert hotkey._parse_gsettings_list(value) == expected


# ---- GNOME

class FakeGsettings:
    def __init__(self, bindings="['/custom0/']", fail_on=None):
        self.values = {("get", hotkey._GNOME_SCHEMA, hotkey._GNOME_LIST_KEY): bindings}
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, args, **_kwargs):
        cmd = tuple(args[1:])
        self.calls.append(cmd)
        if self.fail_on and cmd[0] == self.fail_on:
            raise subprocess.CalledProcessError(1, args)
        if cmd[0] == "set" and cmd[2] == hotkey._GNOME_LIST_KEY:
            self.values[("get", hotkey._GNOME_SCHEMA, hotkey._GNOME_LIST_KEY)] = cmd[3]
        return SimpleNamespace(stdout=self.values.get(cmd, ""))


@pytest.fixture
def tools_available():
    with patch.object(hotkey.shutil, "which", return_value="/usr/bin/tool"):
        yield


def test_gnome_start_registers_shortcut_running_curl(tools_available):
    gsettings = FakeGsettings()
    GnomeHotkey("F9", run=gsettings).start(lambda: None, URL)
    assert ("set", hotkey._GNOME_SCHEMA, hotkey._GNOME_LIST_KEY, str(["/custom0/", PATH])) in gsettings.calls
    assert ("set", SCHEMA, "command", f"curl -s -X POST {URL}") in gsettings.calls
    assert ("set", SCHEMA, "binding", "F9") in gsettings.calls


def test_gnome_start_does_not_duplicate_existing_shortcut(tools_available):
    gsettings = FakeGsettings(bindings=str([PATH]))
    GnomeHotkey("F2", run=gsettings).start(lambda: None, URL)
    assert not any(c[0] == "set" and c[2] == hotkey._GNOME_LIST_KEY for c in gsettings.calls)


def test_gnome_stop_removes_shortcut(tools_available):
    gsettings = FakeGsettings(bindings="@as []")
    key = GnomeHotkey("F9", run=gsettings)
    key.start(lambda: None, URL)
    key.stop()
    assert gsettings.values[("get", hotkey._GNOME_SCHEMA, hotkey._GNOME_LIST_KEY)] == "[]"
    assert ("reset", SCHEMA, "binding") in gsettings.calls
    calls = len(gsettings.calls)
    key.stop()  # idempotent
    assert len(gsettings.calls) == calls


def test_gnome_stop_ignores_gsettings_errors(tools_available):
    gsettings = FakeGsettings()
    key = GnomeHotkey("F9", run=gsettings)
    key.start(lambda: None, URL)
    gsettings.fail_on = "get"
    key.stop()


def test_gnome_without_gsettings_explains_manual_binding():
    with patch.object(hotkey.shutil, "which", return_value=None):
        with pytest.raises(HotkeyError, match="curl -s -X POST"):
            GnomeHotkey("F9", run=FakeGsettings()).start(lambda: None, URL)


def test_gnome_gsettings_failure_raises(tools_available):
    with pytest.raises(HotkeyError, match="Could not register"):
        GnomeHotkey("F9", run=FakeGsettings(fail_on="set")).start(lambda: None, URL)


# ---- macOS (fake Quartz)

def _fake_quartz(listen_access=True, tap=object()):
    q = MagicMock()
    q.kCGEventKeyDown = 10
    q.kCGEventTapDisabledByTimeout = 0xFFFFFFFE
    q.kCGEventTapDisabledByUserInput = 0xFFFFFFFF
    q.CGPreflightListenEventAccess.return_value = listen_access
    q.CGEventTapCreate.return_value = tap
    # The run loop must return, or the listener thread would block forever in the test.
    q.CFRunLoopRun.return_value = None
    return q


def _macos_hotkey(quartz, key="F9"):
    with patch.dict("sys.modules", {"Quartz": quartz}):
        return MacOSHotkey(key)


def test_macos_without_permission_asks_for_it():
    quartz = _fake_quartz(listen_access=False)
    with pytest.raises(HotkeyError, match="Input Monitoring"):
        _macos_hotkey(quartz).start(lambda: None, URL)
    quartz.CGRequestListenEventAccess.assert_called_once()


def test_macos_tap_creation_failure_raises():
    with pytest.raises(HotkeyError, match="Input Monitoring"):
        _macos_hotkey(_fake_quartz(tap=None)).start(lambda: None, URL)


def test_macos_listens_to_the_selected_key_only():
    quartz = _fake_quartz()
    fields = {}
    quartz.CGEventGetIntegerValueField.side_effect = lambda event, field: fields[event][field]
    on_press = MagicMock()
    key = _macos_hotkey(quartz, "F9")
    key.start(on_press, URL)
    callback = quartz.CGEventTapCreate.call_args[0][4]
    assert quartz.CGEventTapCreate.call_args[0][2] == quartz.kCGEventTapOptionListenOnly

    def press(keycode, autorepeat=0):
        event = object()
        fields[event] = {quartz.kCGKeyboardEventKeycode: keycode, quartz.kCGKeyboardEventAutorepeat: autorepeat}
        assert callback(None, quartz.kCGEventKeyDown, event, None) is event  # the key still reaches the game

    press(100)                 # F8
    press(101, autorepeat=1)   # F9 held down
    on_press.assert_not_called()
    press(101)                 # F9
    on_press.assert_called_once()


def test_macos_reenables_tap_disabled_by_timeout():
    quartz = _fake_quartz()
    key = _macos_hotkey(quartz)
    key.start(lambda: None, URL)
    callback = quartz.CGEventTapCreate.call_args[0][4]
    quartz.CGEventTapEnable.reset_mock()
    callback(None, quartz.kCGEventTapDisabledByTimeout, object(), None)
    quartz.CGEventTapEnable.assert_called_once_with(quartz.CGEventTapCreate.return_value, True)


def test_macos_stop_stops_run_loop():
    quartz = _fake_quartz()
    key = _macos_hotkey(quartz)
    key.start(lambda: None, URL)
    run_loop = key._run_loop
    key.stop()
    quartz.CFRunLoopStop.assert_called_once_with(run_loop)
    key.stop()  # idempotent
    quartz.CFRunLoopStop.assert_called_once()
