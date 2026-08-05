import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from config import DIR_TEMP
from ocr_mining import frames

_PREVIEW_MAX_SIZE = (800, 450)


# Shows a carousel of candidate frames from the video (in case the first one doesn't happen to have any dialogue on screen) 
# the user drags a rectangle on whichever one they pick to define the subtitle region (normalized (x, y, w, h) fractions).
class OcrRegionDialog(tk.Toplevel):
    def __init__(
        self, parent, video_file: Path,
        initial_region: tuple[float, float, float, float] | None = None,
    ):
        super().__init__(parent)
        self.title("Select subtitle region")
        self.resizable(False, False)
        self.transient(parent)

        self._video_file = video_file
        self._region: tuple[float, float, float, float] | None = initial_region
        self._result: tuple[float, float, float, float] | None = None
        self._preview_images: list[Image.Image] = []
        self._current_index = 0
        self._photo: ImageTk.PhotoImage | None = None
        self._canvas_size = (0, 0)
        self._rect_id: int | None = None
        self._drag_start: tuple[int, int] | None = None

        self._status_lbl = ttk.Label(self, text="Loading preview frames…")
        self._status_lbl.pack(padx=10, pady=10)

        self._canvas = tk.Canvas(self, highlightthickness=0)

        self._nav_row = ttk.Frame(self)
        ttk.Button(self._nav_row, text="◀ Previous", command=self._on_prev).pack(side="left")
        self._nav_lbl = ttk.Label(self._nav_row, text="")
        self._nav_lbl.pack(side="left", padx=8)
        ttk.Button(self._nav_row, text="Next ▶", command=self._on_next).pack(side="left")

        self._btn_row = ttk.Frame(self)
        ttk.Button(self._btn_row, text="Reset to bottom third", command=self._reset_bottom_third).pack(side="left")
        ttk.Button(self._btn_row, text="Full frame", command=self._reset_full_frame).pack(side="left", padx=(8, 0))
        ttk.Button(self._btn_row, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(self._btn_row, text="OK", command=self._on_ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        threading.Thread(target=self._load_previews_bg, daemon=True).start()

    def show(self) -> tuple[float, float, float, float] | None:
        self.grab_set()
        self.wait_window(self)
        return self._result

    def _load_previews_bg(self) -> None:
        preview_dir = DIR_TEMP / "ocr_region_preview"
        try:
            preview_paths = frames.grab_sample_frames(self._video_file, preview_dir)
            width, height = frames.probe_dimensions(self._video_file)
            images = []
            for path in preview_paths:
                image = Image.open(path)
                image.load()
                images.append(image)
        except Exception as exc:
            self.after(0, self._on_preview_failed, str(exc))
            return
        self.after(0, self._on_previews_loaded, images, width, height)

    def _on_preview_failed(self, message: str) -> None:
        self._status_lbl.config(text=f"Could not load preview frames:\n{message}")
        self._btn_row.pack(fill="x", padx=10, pady=(0, 10))

    def _on_previews_loaded(self, images: list[Image.Image], width: int, height: int) -> None:
        self._status_lbl.pack_forget()
        self._preview_images = images

        max_w, max_h = _PREVIEW_MAX_SIZE
        scale = min(max_w / width, max_h / height, 1.0)
        canvas_w, canvas_h = round(width * scale), round(height * scale)
        self._canvas_size = (canvas_w, canvas_h)

        self._canvas.config(width=canvas_w, height=canvas_h)
        self._canvas.pack(padx=10, pady=(0, 10))
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self._nav_row.pack(pady=(0, 10))
        self._btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self._show_current_frame()
        self._draw_region(self._region or frames.DEFAULT_REGION)

    def _show_current_frame(self) -> None:
        canvas_w, canvas_h = self._canvas_size
        image = self._preview_images[self._current_index]
        self._photo = ImageTk.PhotoImage(image.resize((canvas_w, canvas_h)))
        self._canvas.delete("frame_image")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo, tags="frame_image")
        self._canvas.tag_lower("frame_image")
        self._nav_lbl.config(text=f"Frame {self._current_index + 1}/{len(self._preview_images)}")

    def _on_prev(self) -> None:
        if not self._preview_images:
            return
        self._current_index = (self._current_index - 1) % len(self._preview_images)
        self._show_current_frame()

    def _on_next(self) -> None:
        if not self._preview_images:
            return
        self._current_index = (self._current_index + 1) % len(self._preview_images)
        self._show_current_frame()

    def _draw_region(self, region: tuple[float, float, float, float]) -> None:
        canvas_w, canvas_h = self._canvas_size
        x_frac, y_frac, w_frac, h_frac = region
        x0, y0 = x_frac * canvas_w, y_frac * canvas_h
        x1, y1 = x0 + w_frac * canvas_w, y0 + h_frac * canvas_h
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(x0, y0, x1, y1, outline="#ff3b30", width=2)
        self._region = region

    def _clamped_drag_rect(self, end_x: int, end_y: int) -> tuple[int, int, int, int]:
        canvas_w, canvas_h = self._canvas_size
        start_x, start_y = self._drag_start
        left, right = sorted((max(0, min(start_x, canvas_w)), max(0, min(end_x, canvas_w))))
        top, bottom = sorted((max(0, min(start_y, canvas_h)), max(0, min(end_y, canvas_h))))
        return left, top, right, bottom

    def _on_drag_start(self, event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_drag_motion(self, event) -> None:
        if self._drag_start is None:
            return
        left, top, right, bottom = self._clamped_drag_rect(event.x, event.y)
        if self._rect_id is not None:
            self._canvas.delete(self._rect_id)
        self._rect_id = self._canvas.create_rectangle(left, top, right, bottom, outline="#ff3b30", width=2)

    def _on_drag_end(self, event) -> None:
        if self._drag_start is None:
            return
        left, top, right, bottom = self._clamped_drag_rect(event.x, event.y)
        self._drag_start = None
        if right - left < 4 or bottom - top < 4:
            return  # too small to be an intentional selection, ignore
        canvas_w, canvas_h = self._canvas_size
        self._region = (left / canvas_w, top / canvas_h, (right - left) / canvas_w, (bottom - top) / canvas_h)

    def _reset_bottom_third(self) -> None:
        if self._canvas_size != (0, 0):
            self._draw_region(frames.DEFAULT_REGION)

    def _reset_full_frame(self) -> None:
        if self._canvas_size != (0, 0):
            self._draw_region((0.0, 0.0, 1.0, 1.0))

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    def _on_ok(self) -> None:
        self._result = self._region
        self.destroy()
