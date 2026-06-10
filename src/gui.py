import shutil
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

from gui_config import COLORS, WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT
from gui_config import FONT_DEFAULT, FONT_LABEL, FONT_SMALL, FONT_BUTTON_LARGE
import chinese_converter
from language import Language

from gui_components.constants import (
    GITHUB_URL, ROOT,
    _CONVERT_OPTIONS_FOR_SCRIPT, CONVERT_BY_LABEL,
    VOICES_FOR_LANGUAGE, DEFAULT_VOICE_FOR_LANGUAGE,
    PYTHON,
)
from gui_components import AudioPanel, EpubPanel, LogPanel
from gui_components import pipeline


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.configure(bg=COLORS["BG"])
        self.resizable(True, True)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self._setup_style()
        self._build_ui()
        self._audio_panel.preload()
        self._epub_panel.preload()

        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=COLORS["BG"], foreground=COLORS["FG"], font=FONT_DEFAULT)
        style.configure("TFrame",      background=COLORS["BG"])
        style.configure("TLabelframe", background=COLORS["PANEL"], relief="flat", borderwidth=0)
        style.configure("TLabelframe.Label",
                        background=COLORS["PANEL"], foreground=COLORS["ACCENT"],
                        font=FONT_LABEL)
        style.configure("TLabel",      background=COLORS["BG"], foreground=COLORS["FG"])
        style.configure("Dim.TLabel",  background=COLORS["BG"], foreground=COLORS["FG_DIM"])
        style.configure("Epub.TLabel",    background=COLORS["PANEL"], foreground=COLORS["FG"])
        style.configure("EpubDim.TLabel", background=COLORS["PANEL"], foreground=COLORS["FG_DIM"])

        style.configure("TButton",
                        background=COLORS["BTN_BG"], foreground=COLORS["FG"],
                        borderwidth=0, relief="flat", padding=(10, 6))
        style.map("TButton",
                  background=[("active", COLORS["BTN_ACT"])],
                  foreground=[("disabled", COLORS["FG_DIM"])])

        style.configure("Start.TButton",
                        background=COLORS["START"], foreground=COLORS["START_FG"],
                        font=FONT_BUTTON_LARGE, padding=(10, 10))
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

        # Language / conversion row
        lang_row = tk.Frame(outer, bg=c["BG"])
        lang_row.pack(fill="x", pady=(0, 8))
        ttk.Label(lang_row, text="Language :").pack(side="left", padx=(0, 8))
        self._lang_var = tk.StringVar(value=Language.MANDARIN_TW.value.label)
        self._lang_combo = ttk.Combobox(
            lang_row, textvariable=self._lang_var,
            values=Language.all_labels(), state="readonly", width=34,
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

        # Mode / precision row
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

        # Panels
        self._audio_panel = AudioPanel(outer, c)
        self._audio_panel.pack(fill="x", pady=(0, 10))

        # Voice selector — only shown in "Generate audio" mode
        self._voice_lf = ttk.LabelFrame(outer, text="  Voice", padding=10)
        voice_row = tk.Frame(self._voice_lf, bg=c["PANEL"])
        voice_row.pack(fill="x")
        _init_lang = Language.MANDARIN_TW
        self._voice_var = tk.StringVar(value=DEFAULT_VOICE_FOR_LANGUAGE[_init_lang])
        self._voice_combo = ttk.Combobox(
            voice_row, textvariable=self._voice_var,
            values=[lbl for lbl, _ in VOICES_FOR_LANGUAGE[_init_lang]],
            state="readonly", width=42,
        )
        self._voice_combo.pack(side="left")

        self._epub_panel = EpubPanel(outer, c)
        self._epub_panel.pack(fill="x", pady=(0, 14))

        # Start / clear row
        self._start_row = tk.Frame(outer, bg=c["BG"])
        self._start_row.pack(fill="x", pady=(0, 10))
        self._start_btn = ttk.Button(
            self._start_row, text="Start",
            style="Start.TButton", command=self._start,
        )
        self._start_btn.pack(side="left", fill="x", expand=True)
        ttk.Button(self._start_row, text="Clear output",
                   command=self._clear_output).pack(side="left", padx=(8, 0))

        # Progress bar + status label
        prog_frame = tk.Frame(outer, bg=c["BG"])
        prog_frame.pack(fill="x", pady=(0, 10))
        self._progress = ttk.Progressbar(prog_frame, mode="determinate", maximum=100, value=0)
        self._progress.pack(fill="x")
        self._status_lbl = ttk.Label(prog_frame, text="", style="Dim.TLabel", font=FONT_SMALL)
        self._status_lbl.pack(anchor="w", pady=(3, 0))

        # Footer
        footer = tk.Frame(outer, bg=c["BG"])
        footer.pack(side="bottom", fill="x")
        gh_lbl = tk.Label(footer, text="Project repository", cursor="hand2",
                          bg=c["BG"], fg=c["ACCENT"], font=FONT_SMALL)
        gh_lbl.pack(side="right", padx=4, pady=(2, 4))
        gh_lbl.bind("<Button-1>", lambda _: webbrowser.open(GITHUB_URL))

        # Log
        self._log_panel = LogPanel(outer, c)
        self._log_panel.pack(fill="both", expand=True)

    # ----- event handlers -----

    def _convert_labels_for(self, lang: Language) -> list[str]:
        script = chinese_converter.SCRIPT_FOR_LANGUAGE.get(lang)
        if script is None:
            return ["No conversion"]
        return [label for label, _ in _CONVERT_OPTIONS_FOR_SCRIPT[script]]

    def _on_lang_change(self, *_) -> None:
        lang = Language.from_label(self._lang_var.get())
        labels = self._convert_labels_for(lang)
        self._convert_combo["values"] = labels
        self._convert_var.set("No conversion")
        self._convert_combo.config(state="readonly" if len(labels) > 1 else "disabled")
        voices = VOICES_FOR_LANGUAGE.get(lang, [])
        self._voice_combo["values"] = [lbl for lbl, _ in voices]
        self._voice_var.set(DEFAULT_VOICE_FOR_LANGUAGE.get(lang, voices[0][0] if voices else ""))

    def _on_mode_change(self, *_) -> None:
        mode = self._mode_var.get()
        if mode == "Generate audio":
            self._precision_lbl.pack_forget()
            self._precision_combo.pack_forget()
        else:
            if not self._precision_lbl.winfo_ismapped():
                self._precision_lbl.pack(side="left", padx=(16, 8))
                self._precision_combo.pack(side="left")

        self._audio_panel.pack_forget()
        self._voice_lf.pack_forget()
        self._epub_panel.pack_forget()
        if mode == "Standard":
            self._audio_panel.pack(fill="x", pady=(0, 10),  before=self._start_row)
            self._epub_panel.pack(fill="x",  pady=(0, 14),  before=self._start_row)
        elif mode == "Generate subtitles":
            self._audio_panel.pack(fill="x", pady=(0, 10),  before=self._start_row)
        elif mode == "Generate audio":
            self._voice_lf.pack(fill="x",    pady=(0, 10),  before=self._start_row)
            self._epub_panel.pack(fill="x",  pady=(0, 14),  before=self._start_row)

    def _start(self) -> None:
        mode = self._mode_var.get()
        if mode != "Generate audio" and not self._audio_panel.files:
            messagebox.showwarning("Missing files", "Add at least one audio file (MP3 or M4B).")
            return
        if mode != "Generate subtitles" and self._epub_panel.epub_file is None:
            messagebox.showwarning("Missing file", "Select an EPUB or TXT file.")
            return
        selected_chapters: list[int] = []
        if mode != "Generate subtitles":
            selected_chapters = list(self._epub_panel.selected_indices)
            if self._epub_panel.chapters and not selected_chapters:
                messagebox.showwarning("No chapters selected", "Select at least one chapter.")
                return

        for w in (self._start_btn, self._lang_combo, self._convert_combo,
                  self._precision_combo, self._mode_combo, self._voice_combo):
            w.config(state="disabled")
        self._log_panel.clear()
        self._set_status("Preparing…", 0)

        threading.Thread(
            target=pipeline.run_pipeline,
            kwargs=dict(
                python_exe=PYTHON,
                mode=mode,
                lang=Language.from_label(self._lang_var.get()),
                model=self._precision_var.get().split()[0].lower(),
                convert_target=CONVERT_BY_LABEL.get(self._convert_var.get()),
                voice_label=self._voice_var.get(),
                audio_files=list(self._audio_panel.files),
                epub_file=self._epub_panel.epub_file,
                epub_chapters=list(self._epub_panel.chapters),
                selected_chapters=selected_chapters,
                schedule=self.after,
                log=self._log_panel.write,
                set_status=self._set_status,
                on_done=self._on_done,
                on_finish=self._on_finish,
            ),
            daemon=True,
        ).start()

    def _on_done(self) -> None:
        if messagebox.askyesno("Done", "Processing complete!\n\nOpen the output folder?"):
            subprocess.run(["open", str(ROOT / "output" / "final")])

    def _on_finish(self) -> None:
        self._start_btn.config(state="normal")
        self._lang_combo.config(state="readonly")
        self._convert_combo.config(state="readonly")
        self._precision_combo.config(state="readonly")
        self._mode_combo.config(state="readonly")
        self._voice_combo.config(state="readonly")

    def _clear_output(self) -> None:
        if not messagebox.askyesno(
            "Clear output",
            "This will delete all files in the output folder.\n\nAre you sure?",
        ):
            return
        output_dir = ROOT / "output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._log_panel.write("Output folder cleared.\n")

    def _set_status(self, text: str, pct: float) -> None:
        self._status_lbl.config(text=text)
        self._progress["value"] = pct


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
