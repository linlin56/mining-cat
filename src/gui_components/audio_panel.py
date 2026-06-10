from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from gui_config import FONT_LISTBOX
from gui_components.constants import DIR_AUDIOBOOK
from config import AUDIO_EXTENSIONS, glob_audio_files


class AudioPanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        exts = ", ".join(e.upper() for e in AUDIO_EXTENSIONS)
        super().__init__(parent, text=f"  Audio files  ({exts})", padding=10, **kwargs)
        self._colors = colors
        self._files: list[Path] = []
        self._build()

    @property
    def files(self) -> list[Path]:
        return self._files

    def _build(self) -> None:
        c = self._colors
        list_frame = tk.Frame(self, bg=c["PANEL"])
        list_frame.pack(fill="x")

        self._lb = tk.Listbox(
            list_frame, height=5, selectmode=tk.EXTENDED,
            bg=c["BG"], fg=c["FG"], selectbackground=c["ACCENT"],
            selectforeground=c["BG"], relief="flat", borderwidth=0,
            highlightthickness=0, font=FONT_LISTBOX, activestyle="none",
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._lb.yview)
        self._lb.config(yscrollcommand=sb.set)
        self._lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btn_row = tk.Frame(self, bg=c["PANEL"])
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="+ Add files",          command=self._add).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="− Remove selection",   command=self._remove).pack(side="left")

    def preload(self) -> None:
        for f in glob_audio_files(DIR_AUDIOBOOK):
            if f not in self._files:
                self._files.append(f)
                self._lb.insert(tk.END, f.name)

    def _add(self) -> None:
        ext_pattern = " ".join(f"*.{e}" for e in AUDIO_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[("Audio", ext_pattern), ("All", "*.*")],
        )
        for p in paths:
            path = Path(p)
            if path not in self._files:
                self._files.append(path)
                self._lb.insert(tk.END, path.name)

    def _remove(self) -> None:
        for i in reversed(self._lb.curselection()):
            self._lb.delete(i)
            del self._files[i]
