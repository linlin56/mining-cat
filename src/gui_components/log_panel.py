import tkinter as tk
from tkinter import ttk

from gui_config import FONT_MONO


class LogPanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, text="  Log", padding=6, **kwargs)
        self._colors = colors
        self._build()

    def _build(self) -> None:
        c = self._colors
        inner = tk.Frame(self, bg=c["BG"])
        inner.pack(fill="both", expand=True)

        self._text = tk.Text(
            inner, state="disabled", wrap="word",
            bg=c["BG"], fg=c["FG"], insertbackground=c["FG"],
            font=FONT_MONO, relief="flat", borderwidth=0,
            highlightthickness=0,
        )
        sb = ttk.Scrollbar(inner, orient="vertical", command=self._text.yview)
        self._text.config(yscrollcommand=sb.set)
        self._text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def write(self, text: str) -> None:
        self._text.config(state="normal")
        self._text.insert(tk.END, text)
        self._text.see(tk.END)
        self._text.config(state="disabled")

    def clear(self) -> None:
        self._text.config(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.config(state="disabled")
