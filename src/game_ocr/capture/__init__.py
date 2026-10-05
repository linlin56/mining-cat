import importlib
import sys
from dataclasses import dataclass

from game_ocr.capture.base import CaptureBackend, CaptureError, WindowInfo


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
        module="game_ocr.capture.linux_wayland",
        class_name="WaylandPortalCapture",
    ),
    BackendInfo(
        id="macos",
        label="macOS",
        platforms=("darwin",),
        module="game_ocr.capture.macos",
        class_name="MacOSCapture",
    ),
)


def backend_info(platform: str | None = None) -> BackendInfo | None:
    platform = platform or sys.platform
    return next((b for b in BACKENDS if platform in b.platforms), None)


def create_backend(platform: str | None = None) -> CaptureBackend:
    platform = platform or sys.platform
    info = backend_info(platform)
    if info is None:
        supported = ", ".join(b.label for b in BACKENDS)
        raise CaptureError(f"Video game / screen share capture isn't supported on '{platform}' yet (supported: {supported}).")
    module = importlib.import_module(info.module)
    return getattr(module, info.class_name)()


__all__ = ["BACKENDS", "BackendInfo", "CaptureBackend", "CaptureError", "WindowInfo", "backend_info", "create_backend"]
