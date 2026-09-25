import os
import queue

from PIL import Image

from game_ocr.capture.base import CaptureBackend, CaptureError, WindowInfo

PERMISSION_HINT = (
    "MiningCat needs the Screen Recording permission to capture a window.\n"
    "Open System Settings > Privacy & Security > Screen & System Audio Recording, "
    "enable the app you launched MiningCat from (Terminal, iTerm2, VS Code...), then restart that app."
)

# ScreenCaptureKit error code when the user declined (or never granted) the Screen Recording permission.
_SCK_ERROR_USER_DECLINED = -3801

# Ignore tiny helper windows (status bar items, tooltips...) that can't be a game window.
_MIN_WINDOW_SIZE = 50

_TIMEOUT_S = 5


def _cgimage_to_pil(cg_image, Quartz) -> Image.Image:
    width = Quartz.CGImageGetWidth(cg_image)
    height = Quartz.CGImageGetHeight(cg_image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg_image))
    if data is None:
        raise CaptureError("Could not read the captured image")
    return Image.frombuffer("RGBA", (width, height), bytes(data), "raw", "BGRA", bytes_per_row, 1).convert("RGB")


class MacOSCapture(CaptureBackend):
    has_system_picker = False

    def __init__(self):
        try:
            import objc
            import Quartz
            import ScreenCaptureKit
        except ImportError as exc:
            raise CaptureError(f"{exc}\nmacOS capture needs pyobjc: run `make install`.") from exc
        if not hasattr(ScreenCaptureKit, "SCScreenshotManager"):
            raise CaptureError("Video game / screen share capture needs macOS 14 (Sonoma) or later.")
        self._objc = objc
        self._Quartz = Quartz
        self._SCK = ScreenCaptureKit
        self._window: WindowInfo | None = None
        # ScreenCaptureKit filter/config are cached per window size: looking the window up again is slow (~100ms).
        self._sck_cache_key: tuple | None = None
        self._sck_filter = None
        self._sck_config = None

    # CaptureBackend

    def list_windows(self) -> list[WindowInfo]:
        self._ensure_permission()
        Q = self._Quartz
        infos = Q.CGWindowListCopyWindowInfo(
            Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements, Q.kCGNullWindowID,
        ) or []
        own_pid = os.getpid()
        windows = []
        for info in infos:
            bounds = info.get("kCGWindowBounds") or {}
            if info.get("kCGWindowLayer", 0) != 0 or info.get("kCGWindowOwnerPID") == own_pid:
                continue
            if bounds.get("Width", 0) < _MIN_WINDOW_SIZE or bounds.get("Height", 0) < _MIN_WINDOW_SIZE:
                continue
            windows.append(WindowInfo(
                id=int(info["kCGWindowNumber"]),
                owner=str(info.get("kCGWindowOwnerName") or "?"),
                title=str(info.get("kCGWindowName") or ""),
            ))
        return windows

    def select_window(self, window: WindowInfo | None = None) -> None:
        if window is None:
            raise CaptureError("Pick a window from list_windows() first.")
        self._window = window
        self._sck_cache_key = None

    # Window ids only live as long as the window: if the game was restarted, fall back to its app + title, then to its app alone.
    def restore(self, state: dict) -> None:
        if not state.get("owner"):
            raise CaptureError("No window saved: select the window again.")
        saved = WindowInfo(id=int(state.get("id", 0)), owner=state["owner"], title=state.get("title", ""))
        windows = self.list_windows()
        match = (
            next((w for w in windows if w.id == saved.id), None)
            or next((w for w in windows if (w.owner, w.title) == (saved.owner, saved.title)), None)
            or next((w for w in windows if w.owner == saved.owner), None)
        )
        if match is None:
            raise CaptureError(f"Window '{saved.label}' not found: is it open (and not minimized)? Otherwise select the window again.")
        self.select_window(match)

    @property
    def state(self) -> dict:
        if self._window is None:
            return {}
        return {"id": self._window.id, "owner": self._window.owner, "title": self._window.title}

    @property
    def window_label(self) -> str:
        return self._window.label if self._window else ""

    def grab_frame(self) -> Image.Image:
        if self._window is None:
            raise CaptureError("No window selected.")
        with self._objc.autorelease_pool():
            return self._grab_screencapturekit()

    # helpers

    def _ensure_permission(self) -> None:
        Q = self._Quartz
        if not Q.CGPreflightScreenCaptureAccess():
            # Shows the system prompt the first time only, then the permission must be granted in System Settings.
            Q.CGRequestScreenCaptureAccess()
            raise CaptureError(PERMISSION_HINT)

    def _window_bounds(self) -> dict:
        Q = self._Quartz
        infos = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionIncludingWindow, self._window.id) or []
        if not infos or not infos[0].get("kCGWindowBounds"):
            raise CaptureError(f"Window '{self._window.label}' is gone: was it closed?")
        return infos[0]["kCGWindowBounds"]

    def _grab_screencapturekit(self) -> Image.Image:
        SCK = self._SCK
        bounds = self._window_bounds()
        cache_key = (self._window.id, bounds["Width"], bounds["Height"])
        if cache_key != self._sck_cache_key:
            sck_window = self._find_sck_window()
            content_filter = SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(sck_window)
            scale = content_filter.pointPixelScale() or 1.0
            config = SCK.SCStreamConfiguration.alloc().init()
            config.setShowsCursor_(False)
            config.setIgnoreGlobalClipSingleWindow_(True)
            # Full Retina resolution: small in-game text OCRs noticeably better.
            config.setWidth_(round(bounds["Width"] * scale))
            config.setHeight_(round(bounds["Height"] * scale))
            self._sck_filter, self._sck_config, self._sck_cache_key = content_filter, config, cache_key

        results = queue.Queue()

        # Runs on a ScreenCaptureKit dispatch queue: always answer, or _wait() would only fail after its timeout.
        def on_image(cg_image, error):
            try:
                results.put((_cgimage_to_pil(cg_image, self._Quartz) if cg_image is not None else None, error))
            except Exception as exc:
                results.put((None, exc))

        SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
            self._sck_filter, self._sck_config, on_image,
        )
        image, error = self._wait(results)
        if image is None:
            self._raise_sck_error(error)
        return image

    def _find_sck_window(self):
        results = queue.Queue()
        self._SCK.SCShareableContent.getShareableContentWithCompletionHandler_(
            lambda content, error: results.put((content, error)),
        )
        content, error = self._wait(results)
        if content is None:
            self._raise_sck_error(error)
        match = next((w for w in content.windows() if w.windowID() == self._window.id), None)
        if match is None:
            raise CaptureError(f"Window '{self._window.label}' is not capturable: is it open (and not minimized)?")
        return match

    @staticmethod
    def _wait(results: queue.Queue):
        try:
            return results.get(timeout=_TIMEOUT_S)
        except queue.Empty:
            raise CaptureError("macOS didn't return a capture in time (timeout)") from None

    # `error` is an NSError from ScreenCaptureKit, or a Python exception raised while converting the image.
    @staticmethod
    def _raise_sck_error(error) -> None:
        if isinstance(error, Exception):
            raise CaptureError(f"Screen capture failed: {error}") from error
        if error is not None and error.code() == _SCK_ERROR_USER_DECLINED:
            raise CaptureError(PERMISSION_HINT)
        raise CaptureError(f"Screen capture failed: {error.localizedDescription() if error is not None else 'unknown error'}")
