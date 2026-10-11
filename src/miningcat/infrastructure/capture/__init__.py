import importlib
import sys
from dataclasses import dataclass

from miningcat.infrastructure.capture.base import CaptureBackend, CaptureError, WindowInfo


@dataclass(frozen=True)
class BackendInfo:
    id: str
    label: str
    platforms: tuple[str, ...]  # sys.platform values
    module: str
    class_name: str


BACKENDS: tuple[BackendInfo, ...] = (
    BackendInfo(
        id="linux_wayland",
        label="Linux (Tested on Ubuntu, Wayland)",
        platforms=("linux",),
        module="miningcat.infrastructure.capture.linux_wayland",
        class_name="WaylandPortalCapture",
    ),
    BackendInfo(
        id="macos",
        label="macOS",
        platforms=("darwin",),
        module="miningcat.infrastructure.capture.macos",
        class_name="MacOSCapture",
    ),
    BackendInfo(
        id="windows",
        label="Windows",
        platforms=("win32",),
        module="miningcat.infrastructure.capture.windows",
        class_name="WindowsCapture",
    ),
)


# Webcams and capture cards (a console or another computer plugged through HDMI): the same OpenCV code on every OS.
WEBCAM = BackendInfo(
    id="webcam",
    label="Webcam / capture card",
    platforms=("linux", "darwin", "win32"),
    module="miningcat.infrastructure.capture.webcam",
    class_name="WebcamCapture",
)


# Window capture backend of the platform.
def backend_info(platform: str | None = None) -> BackendInfo | None:
    platform = platform or sys.platform
    return next((b for b in BACKENDS if platform in b.platforms), None)


def create_backend(platform: str | None = None) -> CaptureBackend:
    platform = platform or sys.platform
    info = backend_info(platform)
    if info is None:
        supported = ", ".join(b.label for b in BACKENDS)
        raise CaptureError(f"Video game / screen share capture isn't supported on '{platform}' yet (supported: {supported}).")
    return _instantiate(info)


# What the video game source can capture on the platform: windows (its window backend), then webcams / capture cards.
def sources(platform: str | None = None) -> list[BackendInfo]:
    platform = platform or sys.platform
    window = backend_info(platform)
    return ([window] if window else []) + ([WEBCAM] if platform in WEBCAM.platforms else [])


def source_info(backend_id: str | None, platform: str | None = None) -> BackendInfo | None:
    return next((s for s in sources(platform) if s.id == backend_id), None)


# Backend of one of sources(), by id (the `backend` saved in the settings).
def create_source(backend_id: str, platform: str | None = None) -> CaptureBackend:
    info = source_info(backend_id, platform)
    if info is None:
        raise CaptureError(f"Capture source '{backend_id}' isn't available on '{platform or sys.platform}'.")
    return _instantiate(WEBCAM) if info.id == WEBCAM.id else create_backend(platform)


def _instantiate(info: BackendInfo) -> CaptureBackend:
    module = importlib.import_module(info.module)
    return getattr(module, info.class_name)()


__all__ = [
    "BACKENDS", "WEBCAM", "BackendInfo", "CaptureBackend", "CaptureError", "WindowInfo",
    "backend_info", "create_backend", "create_source", "source_info", "sources",
]
