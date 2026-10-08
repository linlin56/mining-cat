"""The window where `game setup` draws the screenshot and text areas on a capture of the game (Tkinter)."""
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from miningcat.domain.ocr.regions import FULL_REGION, Region

SCREENSHOT_AREA_TITLE = "Select the window's full size (screenshot sent to the page)"
TEXT_AREA_TITLE = "Select the text area (read by OCR)"

_PREVIEW_MAX_SIZE = (800, 450)
_OUTLINE = "#ff3b30"


class RegionDialog(tk.Toplevel):
    """Shows an image: the user drags a rectangle on it. Its result is the rectangle as (x, y, width, height)
    fractions of the image, None when cancelled."""

    def __init__(self, parent, image: Image.Image, title: str, default_region: Region = FULL_REGION,
                 initial_region: Region | None = None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        # A dialog transient to a withdrawn window (the CLI's hidden root) is never shown on macOS.
        if parent.winfo_viewable():
            self.transient(parent)
        self.default_region = default_region
        self._region: Region = initial_region or default_region
        self._result: Region | None = None
        self._rect_id: int | None = None
        self._drag_start: tuple[int, int] | None = None

        scale = min(_PREVIEW_MAX_SIZE[0] / image.width, _PREVIEW_MAX_SIZE[1] / image.height, 1.0)
        self._canvas_size = (round(image.width * scale), round(image.height * scale))
        self._photo = ImageTk.PhotoImage(image.resize(self._canvas_size))
        self._canvas = tk.Canvas(self, width=self._canvas_size[0], height=self._canvas_size[1], highlightthickness=0)
        self._canvas.pack(padx=10, pady=10)
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Reset", command=lambda: self._draw_region(self.default_region)).pack(side="left")
        ttk.Button(buttons, text="Full frame", command=lambda: self._draw_region(FULL_REGION)).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._on_ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._draw_region(self._region)

    def show(self) -> Region | None:
        self.grab_set()
        self.wait_window(self)
        return self._result

    def _draw_rectangle(self, left: float, top: float, right: float, bottom: float) -> None:
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(left, top, right, bottom, outline=_OUTLINE, width=2)

    def _draw_region(self, region: Region) -> None:
        width, height = self._canvas_size
        x, y, w, h = region
        self._draw_rectangle(x * width, y * height, (x + w) * width, (y + h) * height)
        self._region = region

    def _clamped_drag_rect(self, end_x: int, end_y: int) -> tuple[int, int, int, int]:
        width, height = self._canvas_size
        start_x, start_y = self._drag_start
        left, right = sorted((max(0, min(start_x, width)), max(0, min(end_x, width))))
        top, bottom = sorted((max(0, min(start_y, height)), max(0, min(end_y, height))))
        return left, top, right, bottom

    def _on_drag_start(self, event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_drag_motion(self, event) -> None:
        if self._drag_start is not None:
            self._draw_rectangle(*self._clamped_drag_rect(event.x, event.y))

    def _on_drag_end(self, event) -> None:
        if self._drag_start is None:
            return
        left, top, right, bottom = self._clamped_drag_rect(event.x, event.y)
        self._drag_start = None
        if right - left < 4 or bottom - top < 4:
            return  # too small to be an intentional selection
        width, height = self._canvas_size
        self._region = (left / width, top / height, (right - left) / width, (bottom - top) / height)

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    def _on_ok(self) -> None:
        self._result = self._region
        self.destroy()


def pick_region(image: Image.Image, title: str, default_region: Region = FULL_REGION,
                initial_region: Region | None = None) -> Region | None:
    """Runs a RegionDialog on its own hidden Tk root (the CLI has no window of its own)."""
    root = tk.Tk()
    root.withdraw()
    try:
        return RegionDialog(root, image, title, default_region, initial_region).show()
    finally:
        root.destroy()
