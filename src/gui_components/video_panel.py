import tkinter as tk
from tkinter import ttk

TARGET_WEBSITES = ["Instagram", "YouTube"]


class VideoPanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, text="  Video source", padding=10, **kwargs)
        self._colors = colors
        self._build()

    @property
    def website(self) -> str:
        return self._website_var.get()

    @property
    def url(self) -> str:
        return self._url_var.get().strip()

    def _build(self) -> None:
        c = self._colors
        site_row = tk.Frame(self, bg=c["PANEL"])
        site_row.pack(fill="x")
        ttk.Label(site_row, text="Target website :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._website_var = tk.StringVar(value=TARGET_WEBSITES[0])
        self._website_combo = ttk.Combobox(
            site_row, textvariable=self._website_var,
            values=TARGET_WEBSITES, state="readonly", width=20,
        )
        self._website_combo.pack(side="left")

        url_row = tk.Frame(self, bg=c["PANEL"])
        url_row.pack(fill="x", pady=(8, 0))
        ttk.Label(url_row, text="URL :", style="Epub.TLabel").pack(side="left", padx=(0, 8))
        self._url_var = tk.StringVar()
        self._url_entry = ttk.Entry(url_row, textvariable=self._url_var, width=60)
        self._url_entry.pack(side="left", fill="x", expand=True)
