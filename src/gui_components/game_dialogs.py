import tkinter as tk
from tkinter import ttk
from typing import Callable

from PIL import Image

from game_ocr.capture import WindowInfo
from game_ocr.settings import FULL_REGION, Region
from gui_components.ocr_region_dialog import OcrRegionDialog

SCREENSHOT_AREA_TITLE = "Select the window's full size (screenshot sent to the page)"
TEXT_AREA_TITLE = "Select the text area (read by OCR)"


# Same rectangle-drawing dialog as the hardsubs region, on a single window capture instead of video frames.
class WindowRegionDialog(OcrRegionDialog):
    def __init__(
        self, parent, image: Image.Image, title: str,
        default_region: Region = FULL_REGION, initial_region: Region | None = None,
    ):
        self._image = image
        self.window_title = title
        self.default_region = default_region
        super().__init__(parent, video_file=None, initial_region=initial_region)

    # The capture is already in memory: no background loading (which also needs a running mainloop, absent in the CLI).
    def _start_loading(self) -> None:
        self._on_previews_loaded([self._image], self._image.width, self._image.height)


# Lists the windows a backend without a system picker can capture (macOS), so the user can pick the game.
class WindowPickerDialog(tk.Toplevel):
    def __init__(self, parent, list_windows: Callable[[], list[WindowInfo]], error_handler: Callable[[Exception], None]):
        super().__init__(parent)
        self.title("Select the game window")
        self.resizable(False, False)
        if parent.winfo_viewable():
            self.transient(parent)
        self._list_windows = list_windows
        self._error_handler = error_handler
        self._windows: list[WindowInfo] = []
        self._result: WindowInfo | None = None

        ttk.Label(self, text="Pick the window to capture (it must be open, and not minimized):").pack(
            anchor="w", padx=10, pady=(10, 6),
        )
        self._listbox = tk.Listbox(self, width=70, height=14, activestyle="none", exportselection=False)
        self._listbox.pack(padx=10)
        self._listbox.bind("<Double-Button-1>", lambda _e: self._on_ok())

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=10)
        ttk.Button(btn_row, text="Refresh", command=self._refresh).pack(side="left")
        ttk.Button(btn_row, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(btn_row, text="OK", command=self._on_ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._refresh()

    def show(self) -> WindowInfo | None:
        self.grab_set()
        self.wait_window(self)
        return self._result

    def _refresh(self) -> None:
        try:
            self._windows = self._list_windows()
        except Exception as exc:
            self._error_handler(exc)
            return
        self._listbox.delete(0, "end")
        for window in self._windows:
            self._listbox.insert("end", window.label)

    def _on_ok(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            return
        self._result = self._windows[selection[0]]
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()


# For the CLI: runs a region dialog on its own hidden Tk root.
def pick_region_standalone(
    image: Image.Image, title: str, default_region: Region = FULL_REGION, initial_region: Region | None = None,
) -> Region | None:
    root = tk.Tk()
    root.withdraw()
    try:
        return WindowRegionDialog(root, image, title, default_region, initial_region).show()
    finally:
        root.destroy()
