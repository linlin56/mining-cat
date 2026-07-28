import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

TARGET_WEBSITES = ["Instagram", "YouTube"]
INPUT_MODES = ["From web", "Local file"]
VIDEO_FILETYPES = [
    ("Video", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
    ("All", "*.*"),
]

_CHANNEL_LABELS = {1: "mono", 2: "stereo"}


class VideoPanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, text="  Video source", padding=10, **kwargs)
        self._colors = colors
        self._video_file: Path | None = None
        self._tracks: list[dict] = []
        self._track_by_label: dict[str, int] = {}
        self._ocr_region: tuple[float, float, float, float] | None = None
        self._build()

    @property
    def is_local(self) -> bool:
        return self._mode_var.get() == "Local file"

    @property
    def website(self) -> str:
        return self._website_var.get()

    @property
    def url(self) -> str:
        return self._url_var.get().strip()

    @property
    def video_file(self) -> Path | None:
        return self._video_file

    # Index of the audio track the user picked, or None if there's only one (no need to map it).
    @property
    def audio_track(self) -> int | None:
        if len(self._tracks) <= 1:
            return None
        return self._track_by_label.get(self._audio_track_var.get())

    @property
    def use_ocr(self) -> bool:
        return self._ocr_var.get()

    # Normalized (x, y, w, h) region fractions the user selected, or None
    # (caller/CLI applies the bottom-third default) if never picked.
    @property
    def ocr_region(self) -> tuple[float, float, float, float] | None:
        return self._ocr_region

    def _build(self) -> None:
        c = self._colors
        mode_row = tk.Frame(self, bg=c["PANEL"])
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text="Input source :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._mode_var = tk.StringVar(value=INPUT_MODES[0])
        self._mode_combo = ttk.Combobox(
            mode_row, textvariable=self._mode_var,
            values=INPUT_MODES, state="readonly", width=20,
        )
        self._mode_combo.pack(side="left")
        self._mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        # "From web" mode
        self._web_frame = tk.Frame(self, bg=c["PANEL"])

        site_row = tk.Frame(self._web_frame, bg=c["PANEL"])
        site_row.pack(fill="x")
        ttk.Label(site_row, text="Target website :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._website_var = tk.StringVar(value=TARGET_WEBSITES[0])
        self._website_combo = ttk.Combobox(
            site_row, textvariable=self._website_var,
            values=TARGET_WEBSITES, state="readonly", width=20,
        )
        self._website_combo.pack(side="left")

        url_row = tk.Frame(self._web_frame, bg=c["PANEL"])
        url_row.pack(fill="x", pady=(8, 0))
        ttk.Label(url_row, text="URL :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._url_var = tk.StringVar()
        self._url_entry = ttk.Entry(url_row, textvariable=self._url_var, width=60)
        self._url_entry.pack(side="left", fill="x", expand=True)

        self._web_frame.pack(fill="x", pady=(8, 0))

        # "Local file" mode
        self._local_frame = tk.Frame(self, bg=c["PANEL"])

        file_row = tk.Frame(self._local_frame, bg=c["PANEL"])
        file_row.pack(fill="x")
        self._file_lbl = ttk.Label(file_row, text="No file selected", style="EpubDim.TLabel")
        self._file_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(file_row, text="Select…", command=self._select_file).pack(side="right")

        self._audio_track_row = tk.Frame(self._local_frame, bg=c["PANEL"])
        ttk.Label(self._audio_track_row, text="Audio track :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._audio_track_var = tk.StringVar()
        self._audio_track_combo = ttk.Combobox(
            self._audio_track_row, textvariable=self._audio_track_var,
            state="readonly", width=30,
        )
        self._audio_track_combo.pack(side="left")

        ocr_row = tk.Frame(self._local_frame, bg=c["PANEL"])
        ocr_row.pack(fill="x", pady=(8, 0))
        self._ocr_var = tk.BooleanVar(value=False)
        self._ocr_check = ttk.Checkbutton(
            ocr_row, text="Use OCR for hardsubs (will not rely on audio track)",
            variable=self._ocr_var, command=self._on_ocr_toggle,
        )
        self._ocr_check.pack(side="left")
        self._ocr_region_btn = ttk.Button(
            ocr_row, text="Please select subtitle region…", command=self._select_ocr_region, state="disabled",
        )
        self._ocr_region_btn.pack(side="left", padx=(8, 0))

    def _on_mode_change(self, *_) -> None:
        if self.is_local:
            self._web_frame.pack_forget()
            self._local_frame.pack(fill="x", pady=(8, 0))
        else:
            self._local_frame.pack_forget()
            self._web_frame.pack(fill="x", pady=(8, 0))

    def _select_file(self) -> None:
        path = filedialog.askopenfilename(title="Select a video file", filetypes=VIDEO_FILETYPES)
        if not path:
            return
        self._video_file = Path(path)
        self._file_lbl.config(text=self._video_file.name, style="Epub.TLabel")
        self._load_audio_tracks()
        # A region drawn for a previous video's frame shouldn't silently apply to a different one.
        self._ocr_region = None

    def _on_ocr_toggle(self) -> None:
        self._ocr_region_btn.config(state="normal" if self.use_ocr else "disabled")

    def _select_ocr_region(self) -> None:
        if self._video_file is None:
            return
        from gui_components.ocr_region_dialog import OcrRegionDialog
        dialog = OcrRegionDialog(self, self._video_file, initial_region=self._ocr_region)
        region = dialog.show()
        if region is not None:
            self._ocr_region = region

    def _load_audio_tracks(self) -> None:
        self._audio_track_row.pack_forget()
        self._tracks = []
        threading.Thread(target=self._load_audio_tracks_bg, daemon=True).start()

    def _load_audio_tracks_bg(self) -> None:
        import video
        try:
            tracks = video.list_audio_tracks(self._video_file)
        except Exception:
            tracks = []
        self.after(0, self._on_audio_tracks_loaded, tracks)

    def _on_audio_tracks_loaded(self, tracks: list[dict]) -> None:
        self._tracks = tracks
        if len(tracks) <= 1:
            self._audio_track_row.pack_forget()
            return
        labels = [self._track_label(t) for t in tracks]
        self._track_by_label = dict(zip(labels, (t["index"] for t in tracks)))
        self._audio_track_combo["values"] = labels
        self._audio_track_var.set(labels[0])
        self._audio_track_row.pack(fill="x", pady=(8, 0))

    @staticmethod
    def _track_label(track: dict) -> str:
        # Prefer the "title" tag (e.g. "Mandarin (Taiwan)") if available
        # The "language" tag alone can't tell apart variants sharing one ISO 639-2 code (Mandarin/Cantonese are all "chi").
        name = track.get("title") or track["language"] or "unknown language"
        parts = [f"Track {track['index']}", name]
        channels = _CHANNEL_LABELS.get(track["channels"])
        if channels:
            parts.append(channels)
        return " - ".join(parts)
