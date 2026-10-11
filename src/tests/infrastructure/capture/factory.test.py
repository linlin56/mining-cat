from unittest.mock import MagicMock, patch

import pytest

from miningcat.infrastructure import capture
from miningcat.infrastructure.capture import CaptureBackend, CaptureError, WindowInfo


# per-OS switch
@pytest.mark.parametrize("platform, expected_id", [
    ("linux", "linux_wayland"), ("darwin", "macos"), ("win32", "windows"),
])
def test_backend_info_picks_the_platform_backend(platform, expected_id):
    assert capture.backend_info(platform).id == expected_id


def test_backend_info_unsupported_platform_returns_none():
    assert capture.backend_info("freebsd") is None


def test_backend_labels():
    assert capture.backend_info("linux").label == "Linux (Tested on Ubuntu, Wayland)"
    assert capture.backend_info("darwin").label == "macOS"
    assert capture.backend_info("win32").label == "Windows"


def test_backend_info_defaults_to_current_platform():
    with patch.object(capture.sys, "platform", "darwin"):
        assert capture.backend_info().id == "macos"


def test_create_backend_unsupported_platform_raises():
    with pytest.raises(CaptureError, match="isn't supported on 'freebsd'"):
        capture.create_backend("freebsd")


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
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
    assert WindowInfo(1, "Launcher", "My Game").label == "Launcher - My Game"


def test_window_label_without_title():
    assert WindowInfo(1, "SampleApp").label == "SampleApp"


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


# capture sources: the window backend, then the webcams
@pytest.mark.parametrize("platform, expected_ids", [
    ("linux", ["linux_wayland", "webcam"]), ("darwin", ["macos", "webcam"]), ("win32", ["windows", "webcam"]),
    ("freebsd", []),
])
def test_sources_are_the_window_backend_then_webcams(platform, expected_ids):
    assert [s.id for s in capture.sources(platform)] == expected_ids


def test_source_info_only_knows_the_platform_sources():
    assert capture.source_info("webcam", "darwin") is capture.WEBCAM
    assert capture.source_info("macos", "darwin").id == "macos"
    assert capture.source_info("linux_wayland", "darwin") is None
    assert capture.source_info(None, "darwin") is None


def test_create_source_webcam():
    fake_cls = MagicMock()
    with patch.object(capture.importlib, "import_module", return_value=MagicMock(WebcamCapture=fake_cls)) as import_module:
        backend = capture.create_source("webcam", "linux")
    import_module.assert_called_once_with("miningcat.infrastructure.capture.webcam")
    assert backend is fake_cls.return_value


def test_create_source_window_backend_goes_through_create_backend():
    with patch.object(capture, "create_backend") as create_backend:
        assert capture.create_source("macos", "darwin") is create_backend.return_value
    create_backend.assert_called_once_with("darwin")


def test_create_source_of_another_platform_raises():
    with pytest.raises(CaptureError, match="'windows' isn't available on 'darwin'"):
        capture.create_source("windows", "darwin")


def test_webcam_module_and_class_exist():
    import importlib
    module = importlib.import_module(capture.WEBCAM.module)
    assert issubclass(getattr(module, capture.WEBCAM.class_name), CaptureBackend)
