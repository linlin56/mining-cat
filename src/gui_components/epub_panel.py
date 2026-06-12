import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from gui_config import FONT_LISTBOX, FONT_SMALL
from gui_components.constants import DIR_EBOOK


class EpubPanel(ttk.LabelFrame):
    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, text="  Book - EPUB (recommended) or TXT", padding=10, **kwargs)
        self._colors = colors
        self._epub_files: list[Path] = []
        self._chapters: list[tuple[str, str]] = []
        self._build()

    @property
    def epub_file(self) -> Path | None:
        return self._epub_files[0] if self._epub_files else None

    @property
    def epub_files(self) -> list[Path]:
        return self._epub_files

    @property
    def chapters(self) -> list[tuple[str, str]]:
        return self._chapters

    @property
    def selected_indices(self) -> tuple[int, ...]:
        return self._lb.curselection()

    def _build(self) -> None:
        c = self._colors
        epub_row = tk.Frame(self, bg=c["PANEL"])
        epub_row.pack(fill="x")

        self._lbl = ttk.Label(epub_row, text="No file selected", style="EpubDim.TLabel")
        self._lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(epub_row, text="Select…", command=self._select).pack(side="right")

        chap_frame = tk.Frame(self, bg=c["PANEL"])
        chap_frame.pack(fill="x", pady=(6, 0))
        self._lb = tk.Listbox(
            chap_frame, height=5, selectmode=tk.EXTENDED,
            bg=c["BG"], fg=c["FG"], selectbackground=c["ACCENT"],
            selectforeground=c["BG"], relief="flat", borderwidth=0,
            highlightthickness=0, font=FONT_LISTBOX, activestyle="none",
        )
        chap_sb = ttk.Scrollbar(chap_frame, orient="vertical", command=self._lb.yview)
        self._lb.config(yscrollcommand=chap_sb.set)
        self._lb.pack(side="left", fill="both", expand=True)
        chap_sb.pack(side="right", fill="y")
        self._lb.bind("<<ListboxSelect>>", self._update_count)

        chap_ctrl = tk.Frame(self, bg=c["PANEL"])
        chap_ctrl.pack(fill="x", pady=(4, 0))
        ttk.Button(chap_ctrl, text="Select all",   command=self.select_all).pack(side="left", padx=(0, 6))
        ttk.Button(chap_ctrl, text="Deselect all", command=self.deselect_all).pack(side="left")
        self._count_lbl = ttk.Label(chap_ctrl, text="", style="Dim.TLabel", font=FONT_SMALL)
        self._count_lbl.pack(side="right")

    def preload(self) -> None:
        epubs = sorted(DIR_EBOOK.glob("*.epub"))
        txts  = sorted(DIR_EBOOK.glob("*.txt"))
        if epubs:
            self._epub_files = [epubs[0]]
        elif txts:
            self._epub_files = txts
        else:
            return
        self._update_label()
        self._load_chapters()

    def _select(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select an EPUB or TXT file(s)",
            filetypes=[("EPUB", "*.epub"), ("Text", "*.txt"), ("All", "*.*")],
        )
        if not paths:
            return
        selected = [Path(p) for p in paths]
        epubs = [p for p in selected if p.suffix.lower() == ".epub"]
        if epubs:
            self._epub_files = [epubs[0]]
        else:
            self._epub_files = sorted(selected)
        self._update_label()
        self._load_chapters()

    def _update_label(self) -> None:
        if not self._epub_files:
            self._lbl.config(text="No file selected", style="EpubDim.TLabel")
        elif len(self._epub_files) == 1:
            self._lbl.config(text=self._epub_files[0].name, style="Epub.TLabel")
        else:
            self._lbl.config(text=f"{len(self._epub_files)} TXT files selected", style="Epub.TLabel")

    def _load_chapters(self) -> None:
        self._lb.config(state="normal")
        self._lb.delete(0, tk.END)
        self._lb.insert(tk.END, "Loading chapters…")
        self._lb.config(state="disabled")
        self._count_lbl.config(text="")
        threading.Thread(target=self._load_chapters_bg, daemon=True).start()

    def _load_chapters_bg(self) -> None:
        try:
            if len(self._epub_files) > 1:
                chapters = []
                for p in self._epub_files:
                    text = p.read_text(encoding="utf-8").strip()
                    if text:
                        chapters.append((p.stem, text))
            elif self._epub_files[0].suffix.lower() == ".txt":
                f = self._epub_files[0]
                chapters = [(f.stem, f.read_text(encoding="utf-8"))]
            else:
                from ebooklib import epub as ebooklib_epub
                import epub as epub_mod
                book = ebooklib_epub.read_epub(str(self._epub_files[0]))
                chapters = epub_mod.extract_chapters(book)
        except Exception:
            chapters = []
        self.after(0, self._on_chapters_loaded, chapters)

    def _on_chapters_loaded(self, chapters: list) -> None:
        self._chapters = chapters
        self._lb.config(state="normal")
        self._lb.delete(0, tk.END)
        for i, (title, _) in enumerate(chapters, 1):
            self._lb.insert(tk.END, f"Ch.{i:03d} - {title}")
        self._lb.select_set(0, tk.END)
        self._update_count()

    def select_all(self) -> None:
        self._lb.select_set(0, tk.END)
        self._update_count()

    def deselect_all(self) -> None:
        self._lb.select_clear(0, tk.END)
        self._update_count()

    def _update_count(self, *_) -> None:
        total = self._lb.size()
        sel = len(self._lb.curselection())
        self._count_lbl.config(text=f"{sel}/{total} chapters" if total else "")
