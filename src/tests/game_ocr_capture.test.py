from unittest.mock import MagicMock, patch

import pytest

from game_ocr import capture
from game_ocr.capture import CaptureBackend, CaptureError, WindowInfo


# per-OS switch
@pytest.mark.parametrize("platform, expected_id", [("linux", "linux_wayland"), ("darwin", "macos")])
def test_backend_info_picks_the_platform_backend(platform, expected_id):
    assert capture.backend_info(platform).id == expected_id


def test_backend_info_unsupported_platform_returns_none():
    assert capture.backend_info("win32") is None


def test_backend_labels():
    assert capture.backend_info("linux").label == "Linux (Tested on Ubuntu, Wayland)"
    assert capture.backend_info("darwin").label == "macOS"


def test_backend_info_defaults_to_current_platform():
    with patch.object(capture.sys, "platform", "darwin"):
        assert capture.backend_info().id == "macos"


def test_create_backend_unsupported_platform_raises():
    with pytest.raises(CaptureError, match="isn't supported on 'win32'"):
        capture.create_backend("win32")


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_create_backend_instantiates_the_registered_class(platform):
    info = capture.backend_info(platform)
    fake_cls = MagicMock()
    fake_module = MagicMock(**{info.class_name: fake_cls})
    with patch.object(capture.importlib, "import_module", return_value=fake_module) as import_module:
        backend = capture.create_backend(platform)
    import_module.assert_called_once_with(info.module)
    assert backend is fake_cls.return_value


def test_registered_modules_and_classes_exist():
    # Imports stay lazy at runtime, but the registry must point at real classes.
    import importlib
    for info in capture.BACKENDS:
        module = importlib.import_module(info.module)
        assert issubclass(getattr(module, info.class_name), CaptureBackend)


# WindowInfo
def test_window_label_with_title():
    assert WindowInfo(1, "Steam", "My Game").label == "Steam - My Game"


def test_window_label_without_title():
    assert WindowInfo(1, "Ryujinx").label == "Ryujinx"


# CaptureBackend base
def test_base_backend_is_abstract():
    backend = CaptureBackend()
    for call in (backend.list_windows, backend.select_window, backend.grab_frame, lambda: backend.restore({})):
        with pytest.raises(NotImplementedError):
            call()
    with pytest.raises(NotImplementedError):
        backend.state
    with pytest.raises(NotImplementedError):
        backend.window_label


def test_base_backend_context_manager_closes():
    backend = CaptureBackend()
    backend.close = MagicMock()
    with backend as entered:
        assert entered is backend
    backend.close.assert_called_once()
