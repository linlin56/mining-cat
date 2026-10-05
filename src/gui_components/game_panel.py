import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from game_ocr import capture
from game_ocr.hotkey import DEFAULT_HOTKEY, HOTKEYS
from game_ocr.settings import GameOcrSettings

_NO_WINDOW = "No window selected"
_NOT_SELECTED = "Not selected"
_POLL_MS = 50


# "Video game / Screen share" source: picks the game window and its two areas (see game_ocr.settings).
# Starting/stopping the capture itself is handled by the owning screen (gui.py), which runs `main.py game serve`.
class GamePanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, text="  Video game / Screen share", padding=10, **kwargs)
        self._colors = colors
        self._settings = GameOcrSettings.load()
        self._backend_info = capture.backend_info()
        # Belongs to another OS (settings file copied over?): it can't be restored here.
        if self._settings.backend is not None and self._backend_info is not None and self._settings.backend != self._backend_info.id:
            self._settings = GameOcrSettings()
        self._busy = False
        self._locked = False
        # Set by the owning screen (gui.py), called whenever the selection changes (e.g. to enable its Start button).
        self.on_change: Callable[[], None] | None = None
        self._build()
        self._refresh()

    @property
    def is_supported(self) -> bool:
        return self._backend_info is not None

    @property
    def is_ready(self) -> bool:
        return self._settings.is_ready

    @property
    def continuous(self) -> bool:
        return self._continuous_var.get()

    @property
    def hotkey(self) -> str:
        return self._hotkey_var.get()

    # Disables the selection buttons while the capture runs: the `game serve` subprocess owns the window and the settings file then.
    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if not locked:
            # The subprocess saved a new Wayland restore token: pick it up.
            self._settings = GameOcrSettings.load()
        self._refresh()

    def _build(self) -> None:
        c = self._colors
        backend_row = tk.Frame(self, bg=c["PANEL"])
        backend_row.pack(fill="x")
        ttk.Label(backend_row, text="Capture :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        label = self._backend_info.label if self._backend_info else "Not supported on this OS yet"
        ttk.Label(backend_row, text=label, style="EpubDim.TLabel").pack(side="left")

        self._window_btn, self._window_lbl = self._button_row("Select window…", self._select_window)
        self._screenshot_btn, self._screenshot_lbl = self._button_row(
            "Select window's full size (for screenshot)…", self._select_screenshot_area,
        )
        self._text_btn, self._text_lbl = self._button_row("Select text area (for OCR)…", self._select_text_area)

        # How captures are triggered: a global key (default), or continuously (which greys out the key).
        trigger_row = tk.Frame(self, bg=c["PANEL"])
        trigger_row.pack(fill="x", pady=(12, 0))
        ttk.Label(trigger_row, text="Capture key :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._hotkey_var = tk.StringVar(value=self._settings.hotkey if self._settings.hotkey in HOTKEYS else DEFAULT_HOTKEY)
        self._hotkey_combo = ttk.Combobox(
            trigger_row, textvariable=self._hotkey_var, values=list(HOTKEYS), state="readonly", width=6,
        )
        self._hotkey_combo.pack(side="left")
        self._hotkey_combo.bind("<<ComboboxSelected>>", self._on_trigger_change)
        self._hotkey_hint = ttk.Label(trigger_row, text="works even with the game focused", style="EpubDim.TLabel")
        self._hotkey_hint.pack(side="left", padx=(10, 0))

        continuous_row = tk.Frame(self, bg=c["PANEL"])
        continuous_row.pack(fill="x", pady=(8, 0))
        self._continuous_var = tk.BooleanVar(value=self._settings.continuous)
        self._continuous_check = ttk.Checkbutton(
            continuous_row, text="Continuous capture (whenever the text changes, instead of the capture key)",
            variable=self._continuous_var, command=self._on_trigger_change,
        )
        self._continuous_check.pack(side="left")

    def _button_row(self, text: str, command: Callable[[], None]) -> tuple[ttk.Button, ttk.Label]:
        row = tk.Frame(self, bg=self._colors["PANEL"])
        row.pack(fill="x", pady=(8, 0))
        button = ttk.Button(row, text=text, command=command, width=40)
        button.pack(side="left")
        label = ttk.Label(row, text="", style="EpubDim.TLabel")
        label.pack(side="left", padx=(10, 0))
        return button, label

    # Keeps the buttons' enabled state and the status labels in sync with the selection.
    def _refresh(self) -> None:
        s = self._settings
        self._window_lbl.config(
            text=s.window_label or _NO_WINDOW,
            style="Epub.TLabel" if s.has_window else "EpubDim.TLabel",
        )
        self._screenshot_lbl.config(
            text="Selected" if s.screenshot_region else ("Whole capture" if s.has_window else _NOT_SELECTED),
            style="Epub.TLabel" if s.screenshot_region else "EpubDim.TLabel",
        )
        self._text_lbl.config(
            text="Selected" if s.text_region else _NOT_SELECTED,
            style="Epub.TLabel" if s.text_region else "EpubDim.TLabel",
        )
        idle = self.is_supported and not self._busy and not self._locked
        self._window_btn.config(state="normal" if idle else "disabled")
        area_state = "normal" if idle and s.has_window else "disabled"
        self._screenshot_btn.config(state=area_state)
        self._text_btn.config(state=area_state)
        self._continuous_check.config(state="disabled" if self._locked else "normal")
        key_usable = not self._locked and not self.continuous
        self._hotkey_combo.config(state="readonly" if key_usable else "disabled")
        if self.on_change is not None:
            self.on_change()

    # Runs `work` in a background thread (portal dialogs and captures block), then `on_success(result)` back on the Tk thread.
    # The thread never touches Tk itself: it hands its outcome over through a queue that the Tk thread polls.
    def _run_bg(self, work: Callable[[], object], on_success: Callable[[object], None]) -> None:
        self._busy = True
        self._refresh()
        outcome: queue.Queue = queue.Queue()

        def target():
            try:
                outcome.put((True, work()))
            except Exception as exc:
                outcome.put((False, exc))

        def poll():
            try:
                ok, value = outcome.get_nowait()
            except queue.Empty:
                self.after(_POLL_MS, poll)
                return
            if ok:
                self._on_bg_done(on_success, value)
            else:
                self._on_bg_error(value)

        threading.Thread(target=target, daemon=True).start()
        self.after(_POLL_MS, poll)

    def _on_bg_done(self, on_success: Callable[[object], None], result: object) -> None:
        self._busy = False
        try:
            on_success(result)
        finally:
            self._refresh()

    def _on_bg_error(self, exc: Exception) -> None:
        self._busy = False
        self._refresh()
        self._show_error(exc)

    def _show_error(self, exc: Exception) -> None:
        messagebox.showerror("Screen capture", str(exc))

    # Remembered for next time, like the window and areas.
    def _on_trigger_change(self, *_) -> None:
        self._settings.hotkey = self.hotkey
        self._settings.continuous = self.continuous
        self._settings.save()
        self._refresh()

    #  window

    def _select_window(self) -> None:
        info = self._backend_info
        try:
            backend = capture.create_backend()
        except Exception as exc:
            self._show_error(exc)
            return

        if backend.has_system_picker:
            # The OS dialog (Wayland portal) blocks until the user answers.
            def work():
                with backend:
                    backend.select_window()
                    return backend.state, backend.window_label
            self._run_bg(work, lambda result: self._on_window_selected(info.id, *result))
            return

        from gui_components.game_dialogs import WindowPickerDialog
        # Fails right away without the screen capture permission: explain it, rather than opening an empty list.
        try:
            backend.list_windows()
        except Exception as exc:
            backend.close()
            self._show_error(exc)
            return
        window = WindowPickerDialog(self, backend.list_windows, self._show_error).show()
        if window is None:
            backend.close()
            return
        with backend:
            backend.select_window(window)
            self._on_window_selected(info.id, backend.state, backend.window_label)
        self._refresh()

    def _on_window_selected(self, backend_id: str, state: dict, label: str) -> None:
        self._settings.set_window(backend_id, state, label)
        self._settings.save()

    # ----- areas -----

    # Captures a fresh frame of the saved window, in the background.
    def _grab_then(self, on_frame: Callable[[object], None]) -> None:
        from game_ocr.session import open_saved_window
        settings = self._settings

        def work():
            with open_saved_window(settings) as backend:
                return backend.grab_frame()

        self._run_bg(work, on_frame)

    def _select_screenshot_area(self) -> None:
        self._grab_then(self._on_screenshot_frame)

    def _on_screenshot_frame(self, frame) -> None:
        from gui_components.game_dialogs import SCREENSHOT_AREA_TITLE, WindowRegionDialog
        region = WindowRegionDialog(self, frame, SCREENSHOT_AREA_TITLE, initial_region=self._settings.screenshot_region).show()
        if region is None:
            return
        self._settings.set_screenshot_region(region)
        self._settings.save()

    def _select_text_area(self) -> None:
        self._grab_then(self._on_text_frame)

    def _on_text_frame(self, frame) -> None:
        from game_ocr.session import crop_region
        from gui_components.game_dialogs import TEXT_AREA_TITLE, WindowRegionDialog
        screenshot = crop_region(frame, self._settings.screenshot_region)
        region = WindowRegionDialog(self, screenshot, TEXT_AREA_TITLE, initial_region=self._settings.text_region).show()
        if region is None:
            return
        self._settings.text_region = region
        self._settings.save()
