# GUI for the project

import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gui_config import COLORS, WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT
from gui_config import FONT_DEFAULT, FONT_LABEL, FONT_SMALL, FONT_MONO, FONT_BUTTON_LARGE, FONT_LISTBOX
import chinese_converter
from language import Language

# Conversion target options per source script.
# s can go to tw / t ; tw can only go to s
_CONVERT_OPTIONS_FOR_SCRIPT: dict[str, list[tuple[str, str | None]]] = {
    "s": [
        ("No conversion", None),
        ("Traditional — Taiwan", "tw"),
        ("Traditional — Chinese", "t"),
    ],
    "tw": [
        ("No conversion", None),
        ("Simplified — China", "s"),
    ],
}
# Flat label ： code lookup used when reading the combo value at pipeline time
_CONVERT_BY_LABEL: dict[str, str | None] = {
    label: code
    for options in _CONVERT_OPTIONS_FOR_SCRIPT.values()
    for label, code in options
}

_GITHUB_URL = "https://github.com/linlin56/audiobook-miner"

# Dirs
ROOT = Path(__file__).parent
DIR_AUDIOBOOK = ROOT / "sources" / "audiobook"
DIR_EBOOK = ROOT / "sources" / "ebook"
DIR_FINAL = ROOT / "output" / "final"

# Run the pipeline with the project venv; fall back to current interpreter.
_VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

STEPS = [
    ("Step 1/4 — Audio preparation",  10,  "audio",     []),
    ("Step 2/4 — EPUB extraction",    25,  "epub",      []),
    ("Step 3/4 — Alignment",          40,  "align",     []),
    ("Step 4/4 — MP4 export",         80,  "export",    ["--all"]),
]

# Whisper-only pipeline: no epub, transcribe directly then export.
STEPS_WHISPER = [
    ("Step 1/3 — Audio preparation",  10,  "audio",      []),
    ("Step 2/3 — Transcription",      40,  "transcribe", []),
    ("Step 3/3 — MP4 export",         80,  "export",     ["--all"]),
]

# TTS pipeline: epub → tts (audio + SRT from sentence boundaries) → export.
# No Whisper alignment needed — edge-tts provides timing directly.
STEPS_TTS = [
    ("Step 1/3 — EPUB extraction",   10,  "epub",   []),
    ("Step 2/3 — Audio + subtitles", 40,  "tts",    []),
    ("Step 3/3 — MP4 export",        80,  "export", ["--all"]),
]

# edge-tts voices per language (no HK/Cantonese, no dialect voices)
_VOICES_FOR_LANGUAGE: dict[Language, list[tuple[str, str]]] = {
    Language.MANDARIN_TW: [
        ("HsiaoChen — Mandarin (Taiwan), female", "zh-TW-HsiaoChenNeural"),
        ("HsiaoYu — Mandarin (Taiwan), female",   "zh-TW-HsiaoYuNeural"),
        ("YunJhe — Mandarin (Taiwan), male",       "zh-TW-YunJheNeural"),
    ],
    Language.MANDARIN_CN: [
        ("Xiaoxiao — Mandarin (China), female",   "zh-CN-XiaoxiaoNeural"),
        ("Xiaoyi — Mandarin (China), female",     "zh-CN-XiaoyiNeural"),
        ("Yunxi — Mandarin (China), male",        "zh-CN-YunxiNeural"),
        ("Yunjian — Mandarin (China), male",      "zh-CN-YunjianNeural"),
        ("Yunxia — Mandarin (China), male",       "zh-CN-YunxiaNeural"),
        ("Yunyang — Mandarin (China), male",      "zh-CN-YunyangNeural"),
    ],
}
_DEFAULT_VOICE_FOR_LANGUAGE: dict[Language, str] = {
    Language.MANDARIN_TW: "HsiaoChen — Mandarin (Taiwan), female",
    Language.MANDARIN_CN: "Xiaoxiao — Mandarin (China), female",
}
_VOICE_ID_BY_LABEL: dict[str, str] = {
    label: voice_id
    for voices in _VOICES_FOR_LANGUAGE.values()
    for label, voice_id in voices
}


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

        style.configure("TCombobox",
                        fieldbackground=COLORS["BTN_BG"], background=COLORS["BTN_BG"],
                        foreground=COLORS["FG"], arrowcolor=COLORS["FG"],
                        selectbackground=COLORS["ACCENT"], selectforeground=COLORS["BG"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", COLORS["BTN_BG"])],
                  foreground=[("readonly", COLORS["FG"])])

        self._colors = dict(
            BG=COLORS["BG"], PANEL=COLORS["PANEL"], ACCENT=COLORS["ACCENT"], FG=COLORS["FG"],
            FG_DIM=COLORS["FG_DIM"], BTN_BG=COLORS["BTN_BG"], START=COLORS["START"],
        )

    def _build_ui(self) -> None:
        c = self._colors
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        lang_row = tk.Frame(outer, bg=c["BG"])
        lang_row.pack(fill="x", pady=(0, 8))
        ttk.Label(lang_row, text="Language :").pack(side="left", padx=(0, 8))
        self._lang_var = tk.StringVar(value=Language.MANDARIN_TW.value.label)
        self._lang_combo = ttk.Combobox(
            lang_row, textvariable=self._lang_var,
            values=Language.all_labels(),
            state="readonly", width=34,
        )
        self._lang_combo.pack(side="left")
        self._lang_combo.bind("<<ComboboxSelected>>", self._on_lang_change)

        ttk.Label(lang_row, text="Convert to :").pack(side="left", padx=(16, 8))
        self._convert_var = tk.StringVar(value="No conversion")
        self._convert_combo = ttk.Combobox(
            lang_row, textvariable=self._convert_var,
            values=self._convert_labels_for(Language.MANDARIN_TW),
            state="readonly", width=30,
        )
        self._convert_combo.pack(side="left")

        precision_row = tk.Frame(outer, bg=c["BG"])
        precision_row.pack(fill="x", pady=(0, 12))

        ttk.Label(precision_row, text="Mode :").pack(side="left", padx=(0, 8))
        self._mode_var = tk.StringVar(value="Standard")
        self._mode_combo = ttk.Combobox(
            precision_row, textvariable=self._mode_var,
            values=["Standard", "Generate subtitles", "Generate audio"],
            state="readonly", width=22,
        )
        self._mode_combo.pack(side="left")
        self._mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self._precision_lbl = ttk.Label(precision_row, text="Precision :")
        self._precision_lbl.pack(side="left", padx=(16, 8))
        self._precision_var = tk.StringVar(value="Base (default)")
        self._precision_combo = ttk.Combobox(
            precision_row, textvariable=self._precision_var,
            values=["Tiny", "Base (default)", "Small", "Medium", "Large"],
            state="readonly", width=18,
        )
        self._precision_combo.pack(side="left")

        self._audio_lf = ttk.LabelFrame(outer, text="  Audio files  (MP3 or M4B)", padding=10)
        self._audio_lf.pack(fill="x", pady=(0, 10))
        audio_lf = self._audio_lf

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

        # Voice selector — only shown in "Generate audio" mode (not packed initially)
        self._voice_lf = ttk.LabelFrame(outer, text="  Voice", padding=10)
        voice_row = tk.Frame(self._voice_lf, bg=c["PANEL"])
        voice_row.pack(fill="x")
        _init_lang = Language.MANDARIN_TW
        self._voice_var = tk.StringVar(value=_DEFAULT_VOICE_FOR_LANGUAGE[_init_lang])
        self._voice_combo = ttk.Combobox(
            voice_row, textvariable=self._voice_var,
            values=[lbl for lbl, _ in _VOICES_FOR_LANGUAGE[_init_lang]],
            state="readonly", width=42,
        )
        self._voice_combo.pack(side="left")

        self._epub_lf = ttk.LabelFrame(outer, text="  Book  (EPUB)", padding=10)
        self._epub_lf.pack(fill="x", pady=(0, 14))
        epub_lf = self._epub_lf

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

        footer = tk.Frame(outer, bg=c["BG"])
        footer.pack(side="bottom", fill="x")
        gh_lbl = tk.Label(footer, text="Project repository", cursor="hand2",
                          bg=c["BG"], fg=c["ACCENT"], font=FONT_SMALL)
        gh_lbl.pack(side="right", padx=4, pady=(2, 4))
        gh_lbl.bind("<Button-1>", lambda _: webbrowser.open(_GITHUB_URL))

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

    def _convert_labels_for(self, lang: Language) -> list[str]:
        script = chinese_converter.SCRIPT_FOR_LANGUAGE.get(lang, "s")
        return [label for label, _ in _CONVERT_OPTIONS_FOR_SCRIPT[script]]

    def _on_lang_change(self, *_) -> None:
        lang = Language.from_label(self._lang_var.get())
        self._convert_combo["values"] = self._convert_labels_for(lang)
        self._convert_var.set("No conversion")
        self._update_voice_options(lang)

    def _update_voice_options(self, lang: Language) -> None:
        voices = _VOICES_FOR_LANGUAGE.get(lang, [])
        self._voice_combo["values"] = [lbl for lbl, _ in voices]
        self._voice_var.set(_DEFAULT_VOICE_FOR_LANGUAGE.get(lang, voices[0][0] if voices else ""))

    def _on_mode_change(self, *_) -> None:
        mode = self._mode_var.get()

        # Precision is only relevant for Whisper modes
        if mode == "Generate audio":
            self._precision_lbl.pack_forget()
            self._precision_combo.pack_forget()
        else:
            if not self._precision_lbl.winfo_ismapped():
                self._precision_lbl.pack(side="left", padx=(16, 8))
                self._precision_combo.pack(side="left")

        # Always reset the three section frames, then re-pack in the right order.
        # Using before=self._start_btn guarantees correct insertion point.
        self._audio_lf.pack_forget()
        self._voice_lf.pack_forget()
        self._epub_lf.pack_forget()
        if mode == "Standard":
            self._audio_lf.pack(fill="x", pady=(0, 10), before=self._start_btn)
            self._epub_lf.pack(fill="x", pady=(0, 14), before=self._start_btn)
        elif mode == "Generate subtitles":
            self._audio_lf.pack(fill="x", pady=(0, 10), before=self._start_btn)
        elif mode == "Generate audio":
            self._voice_lf.pack(fill="x", pady=(0, 10), before=self._start_btn)
            self._epub_lf.pack(fill="x", pady=(0, 14), before=self._start_btn)

    def _start(self) -> None:
        mode = self._mode_var.get()
        if mode != "Generate audio" and not self._audio_files:
            messagebox.showwarning(
                "Missing files", "Add at least one audio file (MP3 or M4B)."
            )
            return
        if mode != "Generate subtitles" and self._epub_file is None:
            messagebox.showwarning(
                "Missing file", "Select an EPUB file."
            )
            return

        self._start_btn.config(state="disabled")
        self._lang_combo.config(state="disabled")
        self._convert_combo.config(state="disabled")
        self._precision_combo.config(state="disabled")
        self._mode_combo.config(state="disabled")
        self._voice_combo.config(state="disabled")
        self._log_clear()
        self._set_status("Preparing…", 0)
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self) -> None:
        lang = Language.from_label(self._lang_var.get())
        convert_target = _CONVERT_BY_LABEL.get(self._convert_var.get())
        model = self._precision_var.get().split()[0].lower()
        mode = self._mode_var.get()

        if mode == "Standard":
            steps = STEPS
        elif mode == "Generate subtitles":
            steps = STEPS_WHISPER
        else:
            steps = STEPS_TTS

        try:
            self._copy_sources()
            for label, pct_start, cmd, extra in steps:
                if cmd in ("align", "transcribe"):
                    extra = extra + ["--language", lang.name.lower(), "--model", model]
                elif cmd == "tts":
                    voice_id = _VOICE_ID_BY_LABEL[self._voice_var.get()]
                    extra = extra + ["--voice", voice_id]
                self.after(0, self._set_status, label + "…", pct_start)
                self.after(0, self._log_write, f"\n{label}\n")
                rc = self._run_cmd([PYTHON, str(ROOT / "main.py"), cmd] + extra)
                if rc != 0:
                    raise RuntimeError(f"Command '{cmd}' failed (code {rc})")
                if cmd in ("align", "tts") and convert_target is not None:
                    source = chinese_converter.SCRIPT_FOR_LANGUAGE[lang]
                    self.after(0, self._set_status, "Step 3.5 — Character conversion…", 45)
                    self.after(0, self._log_write, "\nStep 3.5 — Character conversion\n")
                    chinese_converter.convert_srt_dir(source, convert_target)
                    self.after(0, self._log_write, "  Done.\n")
            self.after(0, self._set_status, "Done", 100)
            self.after(0, self._log_write, "\nPipeline complete.\n")
            self.after(0, self._on_done)
        except Exception as exc:
            self.after(0, self._log_write, f"\n[ERROR] {exc}\n")
            self.after(0, self._set_status, "Error — check the log.", 0)
        finally:
            self.after(0, self._start_btn.config, {"state": "normal"})
            self.after(0, self._lang_combo.config, {"state": "readonly"})
            self.after(0, self._convert_combo.config, {"state": "readonly"})
            self.after(0, self._precision_combo.config, {"state": "readonly"})
            self.after(0, self._mode_combo.config, {"state": "readonly"})
            self.after(0, self._voice_combo.config, {"state": "readonly"})

    def _copy_sources(self) -> None:
        mode = self._mode_var.get()
        self.after(0, self._log_write, "Copying source files\n")

        if mode != "Generate audio":
            audio_outside = [f for f in self._audio_files if f.parent != DIR_AUDIOBOOK]
            if audio_outside:
                _clear_dir(DIR_AUDIOBOOK)
                for f in self._audio_files:
                    shutil.copy2(f, DIR_AUDIOBOOK / f.name)
                    self.after(0, self._log_write, f"  audio : {f.name}\n")
            else:
                self.after(0, self._log_write, "  audio : files already in place\n")

        if mode != "Generate subtitles" and self._epub_file is not None:
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
