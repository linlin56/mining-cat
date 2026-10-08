import contextlib
import ctypes
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from miningcat.infrastructure import hotkeys as hotkey
from miningcat.infrastructure.hotkeys import HotkeyError, gnome, windows
from miningcat.infrastructure.hotkeys.gnome import GnomeHotkey
from miningcat.infrastructure.hotkeys.macos import MacOSHotkey
from miningcat.infrastructure.hotkeys.windows import WindowsHotkey

URL = "http://127.0.0.1:6677/capture"
PATH = gnome._GNOME_BINDING_PATH
SCHEMA = gnome._GNOME_BINDING_SCHEMA


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
    with patch("miningcat.infrastructure.hotkeys.macos.MacOSHotkey") as macos_cls:
        assert hotkey.create_hotkey("F9", "darwin") is macos_cls.return_value
    with patch("miningcat.infrastructure.hotkeys.windows.WindowsHotkey") as windows_cls:
        assert hotkey.create_hotkey("F9", "win32") is windows_cls.return_value
    with pytest.raises(HotkeyError, match="freebsd"):
        hotkey.create_hotkey("F9", "freebsd")


def test_create_hotkey_defaults_to_current_platform():
    with patch.object(hotkey.sys, "platform", "linux"):
        assert isinstance(hotkey.create_hotkey("F9"), GnomeHotkey)


@pytest.mark.parametrize("value, expected", [
    ("@as []\n", []),
    ("['/a/', '/b/']\n", ["/a/", "/b/"]),
])
def test_parse_gsettings_list(value, expected):
    assert gnome._parse_gsettings_list(value) == expected


# ---- GNOME

class FakeGsettings:
    def __init__(self, bindings="['/custom0/']", fail_on=None):
        self.values = {("get", gnome._GNOME_SCHEMA, gnome._GNOME_LIST_KEY): bindings}
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, args, **_kwargs):
        cmd = tuple(args[1:])
        self.calls.append(cmd)
        if self.fail_on and cmd[0] == self.fail_on:
            raise subprocess.CalledProcessError(1, args)
        if cmd[0] == "set" and cmd[2] == gnome._GNOME_LIST_KEY:
            self.values[("get", gnome._GNOME_SCHEMA, gnome._GNOME_LIST_KEY)] = cmd[3]
        return SimpleNamespace(stdout=self.values.get(cmd, ""))


@pytest.fixture
def tools_available():
    with patch.object(gnome.shutil, "which", return_value="/usr/bin/tool"):
        yield


def test_gnome_start_registers_shortcut_running_curl(tools_available):
    gsettings = FakeGsettings()
    GnomeHotkey("F9", run=gsettings).start(lambda: None, URL)
    assert ("set", gnome._GNOME_SCHEMA, gnome._GNOME_LIST_KEY, str(["/custom0/", PATH])) in gsettings.calls
    assert ("set", SCHEMA, "command", f"curl -s -X POST {URL}") in gsettings.calls
    assert ("set", SCHEMA, "binding", "F9") in gsettings.calls


def test_gnome_start_does_not_duplicate_existing_shortcut(tools_available):
    gsettings = FakeGsettings(bindings=str([PATH]))
    GnomeHotkey("F2", run=gsettings).start(lambda: None, URL)
    assert not any(c[0] == "set" and c[2] == gnome._GNOME_LIST_KEY for c in gsettings.calls)


def test_gnome_stop_removes_shortcut(tools_available):
    gsettings = FakeGsettings(bindings="@as []")
    key = GnomeHotkey("F9", run=gsettings)
    key.start(lambda: None, URL)
    key.stop()
    assert gsettings.values[("get", gnome._GNOME_SCHEMA, gnome._GNOME_LIST_KEY)] == "[]"
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
    with patch.object(gnome.shutil, "which", return_value=None):
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


# ---- Windows (fake ctypes.WinDLL)

def _fake_windows_api():
    user32, kernel32 = MagicMock(), MagicMock()
    kernel32.GetCurrentThreadId.return_value = 4242
    user32.SetWindowsHookExW.return_value = 777
    # The real call blocks until a message arrives: return "no more messages" right away so the thread exits in tests.
    user32.GetMessageW.return_value = 0
    return {"user32": user32, "kernel32": kernel32}


# ctypes.WinDLL and ctypes.WINFUNCTYPE only exist on Windows: faked here (with create=True) so the test runs on any OS.
# WINFUNCTYPE is faked as a no-op decorator, so `self._hook_ref` stays the plain Python callback, callable directly.
@contextlib.contextmanager
def _windows_hotkey_modules(dlls):
    with patch.object(windows.ctypes, "WinDLL", lambda name, **_kwargs: dlls[name], create=True), \
         patch.object(windows.ctypes, "WINFUNCTYPE", lambda *_types: (lambda f: f), create=True):
        yield


def _press(callback, vk_code, code=0, message=None):
    info = windows._KBDLLHOOKSTRUCT(vkCode=vk_code)
    return callback(code, message or windows._WM_KEYDOWN, ctypes.addressof(info))


def test_windows_without_api_raises():
    with patch.object(windows.ctypes, "WinDLL", MagicMock(side_effect=OSError("boom")), create=True):
        with pytest.raises(HotkeyError, match="Windows API"):
            WindowsHotkey("F9")


def test_windows_listens_to_the_selected_key_only():
    dlls = _fake_windows_api()
    on_press = MagicMock()
    with _windows_hotkey_modules(dlls):
        key = WindowsHotkey("F9")
        key.start(on_press, URL)
    assert dlls["user32"].SetWindowsHookExW.call_args[0][0] == windows._WH_KEYBOARD_LL
    callback = key._hook_ref

    _press(callback, 0x77)  # F8
    on_press.assert_not_called()
    _press(callback, 0x78)  # F9
    on_press.assert_called_once()


def test_windows_forwards_the_event_to_the_next_hook():
    dlls = _fake_windows_api()
    with _windows_hotkey_modules(dlls):
        key = WindowsHotkey("F9")
        key.start(lambda: None, URL)
    result = _press(key._hook_ref, 0x78)
    assert result is dlls["user32"].CallNextHookEx.return_value


def test_windows_ignores_events_from_a_disabled_hook_code():
    dlls = _fake_windows_api()
    with _windows_hotkey_modules(dlls):
        key = WindowsHotkey("F9")
        on_press = MagicMock()
        key.start(on_press, URL)
    # code != 0 (HC_ACTION): must not read the (possibly meaningless) lparam, just forward the event.
    key._hook_ref(-1, windows._WM_KEYDOWN, 0)
    on_press.assert_not_called()


def test_windows_hook_registration_failure_raises():
    dlls = _fake_windows_api()
    dlls["user32"].SetWindowsHookExW.return_value = 0
    with _windows_hotkey_modules(dlls):
        with pytest.raises(HotkeyError, match="SetWindowsHookExW"):
            WindowsHotkey("F9").start(lambda: None, URL)


def test_windows_pumps_messages_until_none_are_left():
    dlls = _fake_windows_api()
    done = threading.Event()
    calls = []

    def get_message(*_args):
        calls.append(None)
        if len(calls) >= 2:
            done.set()
            return 0
        return 1  # one message, then none: the loop must exit
    dlls["user32"].GetMessageW.side_effect = get_message

    with _windows_hotkey_modules(dlls):
        key = WindowsHotkey("F9")
        key.start(lambda: None, URL)
        assert done.wait(timeout=2)
        key.stop()
    assert len(calls) == 2
    dlls["user32"].TranslateMessage.assert_called_once()
    dlls["user32"].DispatchMessageW.assert_called_once()


def test_windows_stop_unhooks_and_posts_quit():
    dlls = _fake_windows_api()
    with _windows_hotkey_modules(dlls):
        key = WindowsHotkey("F9")
        key.start(lambda: None, URL)
        key.stop()
    dlls["user32"].UnhookWindowsHookEx.assert_called_once_with(777)
    dlls["user32"].PostThreadMessageW.assert_called_once_with(4242, windows._WM_QUIT, 0, 0)
    key.stop()  # idempotent
    dlls["user32"].UnhookWindowsHookEx.assert_called_once()
