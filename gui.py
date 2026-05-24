# GUI for the project

import shutil
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui_config import COLORS, WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT
from gui_config import FONT_DEFAULT, FONT_LABEL, FONT_SMALL, FONT_MONO, FONT_BUTTON_LARGE, FONT_LISTBOX

# Dirs
ROOT = Path(__file__).parent
DIR_AUDIOBOOK = ROOT / "sources" / "audiobook"
DIR_EBOOK = ROOT / "sources" / "ebook"
DIR_FINAL = ROOT / "output" / "final"

# Run the pipeline with the project venv; fall back to current interpreter.
_VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

STEPS = [
    ("Step 1/4 — Audio preparation",  10,  "audio",  []),
    ("Step 2/4 — EPUB extraction",    25,  "epub",   []),
    ("Step 3/4 — Alignment",          40,  "align",  []),
    ("Step 4/4 — MP4 export",         80,  "export", ["--all"]),
]


def _clear_dir(path: Path) -> None:
    if path.exists():
        for f in path.iterdir():
            if f.is_file():
                f.unlink()
    else:
        path.mkdir(parents=True, exist_ok=True)

# The main application class, built with Tkinter.
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.configure(bg=COLORS["BG"])
        self.resizable(True, True)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self._audio_files: list[Path] = []
        self._epub_file: Path | None = None
        self._running = False

        self._setup_style()
        self._build_ui()
        self._preload_sources()

        # macOS: force window to foreground when launched from terminal
        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()
    
    # Set up the Tkinter styles
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=COLORS["BG"], foreground=COLORS["FG"], font=FONT_DEFAULT)
        style.configure("TFrame",      background=COLORS["BG"])
        style.configure("TLabelframe", background=COLORS["PANEL"], relief="flat", borderwidth=0)
        style.configure("TLabelframe.Label",
                        background=COLORS["PANEL"], foreground=COLORS["ACCENT"],
                        font=FONT_LABEL)
        style.configure("TLabel",  background=COLORS["BG"], foreground=COLORS["FG"])
        style.configure("Dim.TLabel", background=COLORS["BG"], foreground=COLORS["FG_DIM"])
        style.configure("Epub.TLabel", background=COLORS["PANEL"], foreground=COLORS["FG"])
        style.configure("EpubDim.TLabel", background=COLORS["PANEL"], foreground=COLORS["FG_DIM"])

        style.configure("TButton",
                        background=COLORS["BTN_BG"], foreground=COLORS["FG"],
                        borderwidth=0, relief="flat", padding=(10, 6))
        style.map("TButton",
                  background=[("active", COLORS["BTN_ACT"])],
                  foreground=[("disabled", COLORS["FG_DIM"])])

        style.configure("Start.TButton",
                        background=COLORS["START"], foreground=COLORS["START_FG"],
                        font=FONT_BUTTON_LARGE,
                        padding=(10, 10))
        style.map("Start.TButton",
                  background=[("active", COLORS["START_HO"]), ("disabled", COLORS["BTN_BG"])],
                  foreground=[("disabled", COLORS["FG_DIM"])])

        style.configure("TProgressbar",
                        troughcolor=COLORS["BTN_BG"], background=COLORS["ACCENT"],
                        thickness=8)

        self._colors = dict(
            BG=COLORS["BG"], PANEL=COLORS["PANEL"], ACCENT=COLORS["ACCENT"], FG=COLORS["FG"],
            FG_DIM=COLORS["FG_DIM"], BTN_BG=COLORS["BTN_BG"], START=COLORS["START"],
        )

    def _build_ui(self) -> None:
        c = self._colors
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        audio_lf = ttk.LabelFrame(outer, text="  Audio files  (MP3 or M4B)", padding=10)
        audio_lf.pack(fill="x", pady=(0, 10))

        list_frame = tk.Frame(audio_lf, bg=c["PANEL"])
        list_frame.pack(fill="x")

        self._audio_lb = tk.Listbox(
            list_frame, height=5, selectmode=tk.EXTENDED,
            bg=c["BG"], fg=c["FG"], selectbackground=c["ACCENT"],
            selectforeground=c["BG"], relief="flat", borderwidth=0,
            highlightthickness=0, font=FONT_LISTBOX,
            activestyle="none",
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self._audio_lb.yview)
        self._audio_lb.config(yscrollcommand=sb.set)
        self._audio_lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btn_row = tk.Frame(audio_lf, bg=c["PANEL"])
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="+ Add files",
                   command=self._add_audio).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="− Remove selection",
                   command=self._remove_audio).pack(side="left")

        epub_lf = ttk.LabelFrame(outer, text="  Book  (EPUB)", padding=10)
        epub_lf.pack(fill="x", pady=(0, 14))

        epub_row = tk.Frame(epub_lf, bg=c["PANEL"])
        epub_row.pack(fill="x")

        self._epub_lbl = ttk.Label(
            epub_row, text="No file selected",
            style="EpubDim.TLabel",
        )
        self._epub_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(epub_row, text="Select…",
                   command=self._select_epub).pack(side="right")

        self._start_btn = ttk.Button(
            outer, text="Start",
            style="Start.TButton", command=self._start,
        )
        self._start_btn.pack(fill="x", pady=(0, 10))

        prog_frame = tk.Frame(outer, bg=c["BG"])
        prog_frame.pack(fill="x", pady=(0, 10))

        self._progress = ttk.Progressbar(
            prog_frame, mode="determinate", maximum=100, value=0,
        )
        self._progress.pack(fill="x")

        self._status_lbl = ttk.Label(
            prog_frame, text="", style="Dim.TLabel",
            font=FONT_SMALL,
        )
        self._status_lbl.pack(anchor="w", pady=(3, 0))

        log_lf = ttk.LabelFrame(outer, text="  Log", padding=6)
        log_lf.pack(fill="both", expand=True)

        log_inner = tk.Frame(log_lf, bg=c["BG"])
        log_inner.pack(fill="both", expand=True)

        self._log = tk.Text(
            log_inner, state="disabled", wrap="word",
            bg=c["BG"], fg=c["FG"], insertbackground=c["FG"],
            font=FONT_MONO, relief="flat", borderwidth=0,
            highlightthickness=0,
        )
        log_sb = ttk.Scrollbar(log_inner, orient="vertical", command=self._log.yview)
        self._log.config(yscrollcommand=log_sb.set)
        self._log.pack(side="left", fill="both", expand=True)
        log_sb.pack(side="right", fill="y")

    def _preload_sources(self) -> None:
        for f in sorted(DIR_AUDIOBOOK.glob("*.mp3")) + sorted(DIR_AUDIOBOOK.glob("*.m4b")):
            if f not in self._audio_files:
                self._audio_files.append(f)
                self._audio_lb.insert(tk.END, f.name)
        epubs = sorted(DIR_EBOOK.glob("*.epub"))
        if epubs:
            self._epub_file = epubs[0]
            self._epub_lbl.config(text=self._epub_file.name, style="Epub.TLabel")

    def _add_audio(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[("Audio", "*.mp3 *.m4b"), ("MP3", "*.mp3"),
                       ("M4B", "*.m4b"), ("All", "*.*")],
        )
        for p in paths:
            path = Path(p)
            if path not in self._audio_files:
                self._audio_files.append(path)
                self._audio_lb.insert(tk.END, path.name)

    def _remove_audio(self) -> None:
        for i in reversed(self._audio_lb.curselection()):
            self._audio_lb.delete(i)
            del self._audio_files[i]

    def _select_epub(self) -> None:
        p = filedialog.askopenfilename(
            title="Select an EPUB file",
            filetypes=[("EPUB", "*.epub"), ("All", "*.*")],
        )
        if p:
            self._epub_file = Path(p)
            self._epub_lbl.config(
                text=self._epub_file.name,
                style="Epub.TLabel",
            )

    def _start(self) -> None:
        if not self._audio_files:
            messagebox.showwarning(
                "Missing files", "Add at least one audio file (MP3 or M4B)."
            )
            return
        if self._epub_file is None:
            messagebox.showwarning(
                "Missing file", "Select an EPUB file."
            )
            return

        self._start_btn.config(state="disabled")
        self._log_clear()
        self._set_status("Preparing…", 0)
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self) -> None:
        try:
            self._copy_sources()
            for label, pct_start, cmd, extra in STEPS:
                self.after(0, self._set_status, label + "…", pct_start)
                self.after(0, self._log_write, f"\n{label}\n")
                rc = self._run_cmd([PYTHON, str(ROOT / "main.py"), cmd] + extra)
                if rc != 0:
                    raise RuntimeError(f"Command '{cmd}' failed (code {rc})")
            self.after(0, self._set_status, "Done", 100)
            self.after(0, self._log_write, "\nPipeline complete.\n")
            self.after(0, self._on_done)
        except Exception as exc:
            self.after(0, self._log_write, f"\n[ERROR] {exc}\n")
            self.after(0, self._set_status, "Error — check the log.", 0)
        finally:
            self.after(0, self._start_btn.config, {"state": "normal"})

    def _copy_sources(self) -> None:
        self.after(0, self._log_write, "Copying source files\n")

        audio_outside = [f for f in self._audio_files if f.parent != DIR_AUDIOBOOK]
        if audio_outside:
            _clear_dir(DIR_AUDIOBOOK)
            for f in self._audio_files:
                shutil.copy2(f, DIR_AUDIOBOOK / f.name)
                self.after(0, self._log_write, f"  audio : {f.name}\n")
        else:
            self.after(0, self._log_write, "  audio : files already in place\n")

        epub_outside = self._epub_file.parent != DIR_EBOOK
        if epub_outside:
            _clear_dir(DIR_EBOOK)
            shutil.copy2(self._epub_file, DIR_EBOOK / self._epub_file.name)
            self.after(0, self._log_write, f"  epub  : {self._epub_file.name}\n")
        else:
            self.after(0, self._log_write, "  epub  : file already in place\n")

    def _run_cmd(self, args: list[str]) -> int:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
        )
        for line in proc.stdout:
            self.after(0, self._log_write, line)
        proc.wait()
        return proc.returncode

    def _on_done(self) -> None:
        if messagebox.askyesno(
            "Done",
            "Processing complete!\n\nOpen the output folder?",
        ):
            subprocess.run(["open", str(DIR_FINAL)])

    def _log_write(self, text: str) -> None:
        self._log.config(state="normal")
        self._log.insert(tk.END, text)
        self._log.see(tk.END)
        self._log.config(state="disabled")

    def _log_clear(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", tk.END)
        self._log.config(state="disabled")

    def _set_status(self, text: str, pct: float) -> None:
        self._status_lbl.config(text=text)
        self._progress["value"] = pct


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
