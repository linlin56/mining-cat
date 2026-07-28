import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

# Visual constants: colors, fonts, window title and minimum dimensions
from gui_config import COLORS, WINDOW_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT
from gui_config import FONT_DEFAULT, FONT_LABEL, FONT_SMALL, FONT_BUTTON_LARGE
# Chinese script conversion utilities (Traditional ↔ Simplified)
import chinese_converter
from language import Language
from frequency import word_frequency, character_frequency

# Shared constants: URLs, file paths, voice/conversion option mappings
from gui_components.constants import (
    GITHUB_URL, ROOT,
    _CONVERT_OPTIONS_FOR_SCRIPT, CONVERT_BY_LABEL,
    VOICES_FOR_LANGUAGE, DEFAULT_VOICE_FOR_LANGUAGE,
    PYTHON,
)
# Reusable UI panels for audio files, epub file, video source, and log output
from gui_components import AudioPanel, EpubPanel, LogPanel, VideoPanel
# Orchestrates the full processing pipeline in a background thread
from gui_components import pipeline
from gui_components.utils import open_folder, srt_to_text


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.configure(bg=COLORS["BG"])
        self.resizable(True, True)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self._last_video_srt: Path | None = None

        self._setup_style()
        self._build_ui()
        self._audio_panel.preload()
        self._epub_panel.preload()
        self._update_video_freq_buttons()

        self.lift()
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
        self.focus_force()

    # Applies the dark theme to all ttk widgets using the "clam" base theme
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

        style.configure("TEntry",
                        fieldbackground=COLORS["BTN_BG"], foreground=COLORS["FG"],
                        insertcolor=COLORS["FG"])

        self._colors = dict(
            BG=COLORS["BG"], PANEL=COLORS["PANEL"], ACCENT=COLORS["ACCENT"], FG=COLORS["FG"],
            FG_DIM=COLORS["FG_DIM"], BTN_BG=COLORS["BTN_BG"], START=COLORS["START"],
        )

    # Creates and lays out all widgets: dropdowns, panels, buttons, progress bar, log
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

        # Precision row
        precision_row = tk.Frame(outer, bg=c["BG"])
        precision_row.pack(fill="x", pady=(0, 8))
        self._precision_lbl = ttk.Label(precision_row, text="Precision :")
        self._precision_lbl.pack(side="left", padx=(0, 8))
        self._precision_var = tk.StringVar(value="Base (default)")
        self._precision_combo = ttk.Combobox(
            precision_row, textvariable=self._precision_var,
            values=["Tiny", "Base (default)", "Small", "Medium", "Large"],
            state="readonly", width=18,
        )
        self._precision_combo.pack(side="left")

        # Source row
        source_row = tk.Frame(outer, bg=c["BG"])
        source_row.pack(fill="x", pady=(0, 12))
        ttk.Label(source_row, text="Source :").pack(side="left", padx=(0, 8))
        self._source_var = tk.StringVar(value="Audiobook / Ebook")
        self._source_combo = ttk.Combobox(
            source_row, textvariable=self._source_var,
            values=["Audiobook / Ebook", "Video"],
            state="readonly", width=22,
        )
        self._source_combo.pack(side="left")
        self._source_combo.bind("<<ComboboxSelected>>", self._on_source_change)

        # ----- Audiobook / Ebook screen -----
        self._audiobook_screen = tk.Frame(outer, bg=c["BG"])

        # Mode row
        mode_row = tk.Frame(self._audiobook_screen, bg=c["BG"])
        mode_row.pack(fill="x", pady=(0, 10))
        ttk.Label(mode_row, text="Mode :").pack(side="left", padx=(0, 8))
        self._mode_var = tk.StringVar(value="Standard")
        self._mode_combo = ttk.Combobox(
            mode_row, textvariable=self._mode_var,
            values=["Standard", "Generate subtitles", "Generate audio"],
            state="readonly", width=22,
        )
        self._mode_combo.pack(side="left")
        self._mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        self._audio_panel = AudioPanel(self._audiobook_screen, c)
        self._audio_panel.pack(fill="x", pady=(0, 10))

        # Voice selector — only shown in "Generate audio" mode
        self._voice_lf = ttk.LabelFrame(self._audiobook_screen, text="  Voice", padding=10)
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

        self._epub_panel = EpubPanel(self._audiobook_screen, c)
        self._epub_panel.pack(fill="x", pady=(0, 10))

        # Frequency lists
        self._freq_lf = ttk.LabelFrame(self._audiobook_screen, text="  Frequency lists", padding=10)
        freq_row = tk.Frame(self._freq_lf, bg=c["PANEL"])
        freq_row.pack(fill="x")
        self._word_freq_btn = ttk.Button(
            freq_row, text="Word frequency", command=self._run_word_frequency,
        )
        self._word_freq_btn.pack(side="left", padx=(0, 8))
        _char_state = "normal" if character_frequency.supports_language(Language.MANDARIN_TW) else "disabled"
        self._char_freq_btn = ttk.Button(
            freq_row, text="Character list", command=self._run_char_frequency,
            state=_char_state,
        )
        self._char_freq_btn.pack(side="left")
        self._freq_lf.pack(fill="x", pady=(0, 14))

        # Start / clear row
        self._start_row = tk.Frame(self._audiobook_screen, bg=c["BG"])
        self._start_row.pack(fill="x", pady=(0, 10))
        self._start_btn = ttk.Button(
            self._start_row, text="Start",
            style="Start.TButton", command=self._start,
        )
        self._start_btn.pack(side="left", fill="x", expand=True)
        ttk.Button(self._start_row, text="Clear output",
                   command=self._clear_output).pack(side="left", padx=(8, 0))

        self._audiobook_screen.pack(fill="x")

        # Video screen (from web or local file) 
        self._video_screen = tk.Frame(outer, bg=c["BG"])

        self._video_panel = VideoPanel(self._video_screen, c)
        self._video_panel.pack(fill="x", pady=(0, 10))

        self._video_freq_lf = ttk.LabelFrame(self._video_screen, text="  Frequency lists", padding=10)
        video_freq_row = tk.Frame(self._video_freq_lf, bg=c["PANEL"])
        video_freq_row.pack(fill="x")
        self._video_word_freq_btn = ttk.Button(
            video_freq_row, text="Word frequency", command=self._run_word_frequency_video,
            state="disabled",
        )
        self._video_word_freq_btn.pack(side="left", padx=(0, 8))
        self._video_char_freq_btn = ttk.Button(
            video_freq_row, text="Character list", command=self._run_char_frequency_video,
            state="disabled",
        )
        self._video_char_freq_btn.pack(side="left")
        self._video_freq_lf.pack(fill="x", pady=(0, 14))

        video_start_row = tk.Frame(self._video_screen, bg=c["BG"])
        video_start_row.pack(fill="x", pady=(0, 10))
        self._video_generate_btn = ttk.Button(
            video_start_row, text="Generate From Source",
            style="Start.TButton", command=self._start_video,
        )
        self._video_generate_btn.pack(side="left", fill="x", expand=True)
        ttk.Button(video_start_row, text="Clear output",
                   command=self._clear_output).pack(side="left", padx=(8, 0))

        # Progress bar + status label
        prog_frame = tk.Frame(outer, bg=c["BG"])
        self._progress_frame = prog_frame
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

    # Returns the list of conversion options available for the given language
    def _convert_labels_for(self, lang: Language) -> list[str]:
        script = chinese_converter.SCRIPT_FOR_LANGUAGE.get(lang)
        if script is None:
            return ["No conversion"]
        return [label for label, _ in _CONVERT_OPTIONS_FOR_SCRIPT[script]]

    # Updates conversion, voice, and character-list button when the user picks a different language
    def _on_lang_change(self, *_) -> None:
        lang = Language.from_label(self._lang_var.get())
        labels = self._convert_labels_for(lang)
        self._convert_combo["values"] = labels
        self._convert_var.set("No conversion")
        self._convert_combo.config(state="readonly" if len(labels) > 1 else "disabled")
        voices = VOICES_FOR_LANGUAGE.get(lang, [])
        self._voice_combo["values"] = [lbl for lbl, _ in voices]
        self._voice_var.set(DEFAULT_VOICE_FOR_LANGUAGE.get(lang, voices[0][0] if voices else ""))
        self._char_freq_btn.config(
            state="normal" if character_frequency.supports_language(lang) else "disabled"
        )
        self._update_video_freq_buttons()

    # Switches between the "Audiobook / Ebook" and "Video" screens
    def _on_source_change(self, *_) -> None:
        source = self._source_var.get()
        if source == "Video":
            if not self._precision_lbl.winfo_ismapped():
                self._precision_lbl.pack(side="left", padx=(0, 8))
                self._precision_combo.pack(side="left")
            self._audiobook_screen.pack_forget()
            self._video_screen.pack(fill="x", before=self._progress_frame)
        else:
            self._video_screen.pack_forget()
            self._audiobook_screen.pack(fill="x", before=self._progress_frame)
            self._on_mode_change()

    # Shows/hides panels and controls depending on the selected processing mode
    def _on_mode_change(self, *_) -> None:
        mode = self._mode_var.get()
        if mode == "Generate audio":
            self._precision_lbl.pack_forget()
            self._precision_combo.pack_forget()
        else:
            if not self._precision_lbl.winfo_ismapped():
                self._precision_lbl.pack(side="left", padx=(0, 8))
                self._precision_combo.pack(side="left")

        self._audio_panel.pack_forget()
        self._voice_lf.pack_forget()
        self._epub_panel.pack_forget()
        self._freq_lf.pack_forget()
        if mode == "Standard":
            self._audio_panel.pack(fill="x", pady=(0, 10),  before=self._start_row)
            self._epub_panel.pack(fill="x",  pady=(0, 10),  before=self._start_row)
            self._freq_lf.pack(fill="x",     pady=(0, 14),  before=self._start_row)
        elif mode == "Generate subtitles":
            self._audio_panel.pack(fill="x", pady=(0, 10),  before=self._start_row)
        elif mode == "Generate audio":
            self._voice_lf.pack(fill="x",    pady=(0, 10),  before=self._start_row)
            self._epub_panel.pack(fill="x",  pady=(0, 10),  before=self._start_row)
            self._freq_lf.pack(fill="x",     pady=(0, 14),  before=self._start_row)

    # Validates inputs, disables controls, then launches the pipeline in a background thread
    def _start(self) -> None:
        mode = self._mode_var.get()
        if mode != "Generate audio" and not self._audio_panel.files:
            messagebox.showwarning("Missing files", "Add at least one audio file (MP3 or M4B).")
            return
        if mode != "Generate subtitles" and not self._epub_panel.epub_files:
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
                epub_files=list(self._epub_panel.epub_files),
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

    # Validates the URL or local file, disables controls, then launches the video pipeline in a background thread
    def _start_video(self) -> None:
        is_local = self._video_panel.is_local
        video_file = self._video_panel.video_file
        url = self._video_panel.url
        if is_local:
            if video_file is None:
                messagebox.showwarning("Missing file", "Select a local video file.")
                return
        elif not url:
            messagebox.showwarning("Missing URL", "Enter a video URL.")
            return

        for w in (self._video_generate_btn, self._lang_combo, self._convert_combo,
                  self._precision_combo, self._source_combo):
            w.config(state="disabled")
        self._log_panel.clear()
        self._set_status("Preparing…", 0)

        threading.Thread(
            target=pipeline.run_video_pipeline,
            kwargs=dict(
                python_exe=PYTHON,
                lang=Language.from_label(self._lang_var.get()),
                model=self._precision_var.get().split()[0].lower(),
                convert_target=CONVERT_BY_LABEL.get(self._convert_var.get()),
                url=None if is_local else url,
                video_path=video_file if is_local else None,
                audio_track=self._video_panel.audio_track if is_local else None,
                use_ocr=self._video_panel.use_ocr,
                ocr_region=self._video_panel.ocr_region,
                schedule=self.after,
                log=self._log_panel.write,
                set_status=self._set_status,
                on_done=self._on_video_done,
                on_finish=self._on_finish,
            ),
            daemon=True,
        ).start()

    def _run_word_frequency(self) -> None:
        all_chapters = self._epub_panel.chapters
        indices = self._epub_panel.selected_indices
        if not all_chapters:
            messagebox.showwarning("No chapters", "Load an EPUB or TXT file first.")
            return
        if not indices:
            messagebox.showwarning("No chapters selected", "Select at least one chapter.")
            return
        chapters = [all_chapters[i] for i in indices]
        lang = Language.from_label(self._lang_var.get())
        epub_file = self._epub_panel.epub_file
        self._word_freq_btn.config(state="disabled")
        threading.Thread(
            target=self._word_freq_bg, args=(chapters, lang, epub_file), daemon=True,
        ).start()

    def _word_freq_bg(self, chapters, lang, epub_file) -> None:
        try:
            text = "\n".join(t for _, t in chapters)
            counter = word_frequency.compute(text, lang)
            out_dir = ROOT / "output" / "frequency"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = epub_file.stem if epub_file else "book"
            out_path = out_dir / f"{stem}_word_freq.csv"
            word_frequency.save_csv(counter, out_path)
            self.after(0, self._on_word_freq_done, out_path, len(counter))
        except Exception as e:
            self.after(0, self._log_panel.write, f"Word frequency error: {e}\n")
            self.after(0, lambda: self._word_freq_btn.config(state="normal"))

    def _on_word_freq_done(self, out_path, n_words) -> None:
        self._word_freq_btn.config(state="normal")
        self._log_panel.write(f"Word frequency: {n_words} unique words → {out_path}\n")
        if messagebox.askyesno("Done", f"Word frequency saved ({n_words} unique words).\n\nOpen output folder?"):
            open_folder(out_path.parent)

    def _run_char_frequency(self) -> None:
        all_chapters = self._epub_panel.chapters
        indices = self._epub_panel.selected_indices
        if not all_chapters:
            messagebox.showwarning("No chapters", "Load an EPUB or TXT file first.")
            return
        if not indices:
            messagebox.showwarning("No chapters selected", "Select at least one chapter.")
            return
        chapters = [all_chapters[i] for i in indices]
        lang = Language.from_label(self._lang_var.get())
        epub_file = self._epub_panel.epub_file
        self._char_freq_btn.config(state="disabled")
        threading.Thread(
            target=self._char_freq_bg, args=(chapters, lang, epub_file), daemon=True,
        ).start()

    def _char_freq_bg(self, chapters, lang, epub_file) -> None:
        try:
            text = "\n".join(t for _, t in chapters)
            counter = character_frequency.compute(text, lang)
            stem = epub_file.stem if epub_file else "book"
            data = character_frequency.build_json(stem, lang, counter)
            out_dir = ROOT / "output" / "frequency"
            out_path = out_dir / f"{stem}_char_list.json"
            character_frequency.save_json(data, out_path)
            self.after(0, self._on_char_freq_done, out_path, len(counter))
        except Exception as e:
            self.after(0, self._log_panel.write, f"Character list error: {e}\n")
            self.after(0, lambda: self._char_freq_btn.config(
                state="normal" if character_frequency.supports_language(
                    Language.from_label(self._lang_var.get())
                ) else "disabled"
            ))

    def _on_char_freq_done(self, out_path, n_chars) -> None:
        self._char_freq_btn.config(state="normal")
        self._log_panel.write(f"Character list: {n_chars} unique characters → {out_path}\n")
        if messagebox.askyesno("Done", f"Character list saved ({n_chars} unique characters).\n\nOpen output folder?"):
            open_folder(out_path.parent)

    # Video: frequency lists (computed from the last generated SRT)

    def _run_word_frequency_video(self) -> None:
        if self._last_video_srt is None or not self._last_video_srt.exists():
            messagebox.showwarning("No video processed", "Generate a video first.")
            return
        lang = Language.from_label(self._lang_var.get())
        srt_path = self._last_video_srt
        self._video_word_freq_btn.config(state="disabled")
        threading.Thread(
            target=self._word_freq_bg_video, args=(srt_path, lang), daemon=True,
        ).start()

    def _word_freq_bg_video(self, srt_path, lang) -> None:
        try:
            text = srt_to_text(srt_path)
            counter = word_frequency.compute(text, lang)
            out_dir = ROOT / "output" / "frequency"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{srt_path.stem}_word_freq.csv"
            word_frequency.save_csv(counter, out_path)
            self.after(0, self._on_word_freq_done_video, out_path, len(counter))
        except Exception as e:
            self.after(0, self._log_panel.write, f"Word frequency error: {e}\n")
            self.after(0, lambda: self._video_word_freq_btn.config(state="normal"))

    def _on_word_freq_done_video(self, out_path, n_words) -> None:
        self._video_word_freq_btn.config(state="normal")
        self._log_panel.write(f"Word frequency: {n_words} unique words → {out_path}\n")
        if messagebox.askyesno("Done", f"Word frequency saved ({n_words} unique words).\n\nOpen output folder?"):
            open_folder(out_path.parent)

    def _run_char_frequency_video(self) -> None:
        if self._last_video_srt is None or not self._last_video_srt.exists():
            messagebox.showwarning("No video processed", "Generate a video first.")
            return
        lang = Language.from_label(self._lang_var.get())
        srt_path = self._last_video_srt
        self._video_char_freq_btn.config(state="disabled")
        threading.Thread(
            target=self._char_freq_bg_video, args=(srt_path, lang), daemon=True,
        ).start()

    def _char_freq_bg_video(self, srt_path, lang) -> None:
        try:
            text = srt_to_text(srt_path)
            counter = character_frequency.compute(text, lang)
            data = character_frequency.build_json(srt_path.stem, lang, counter)
            out_dir = ROOT / "output" / "frequency"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{srt_path.stem}_char_list.json"
            character_frequency.save_json(data, out_path)
            self.after(0, self._on_char_freq_done_video, out_path, len(counter))
        except Exception as e:
            self.after(0, self._log_panel.write, f"Character list error: {e}\n")
            self.after(0, lambda: self._video_char_freq_btn.config(state="normal"))

    def _on_char_freq_done_video(self, out_path, n_chars) -> None:
        self._video_char_freq_btn.config(state="normal")
        self._log_panel.write(f"Character list: {n_chars} unique characters → {out_path}\n")
        if messagebox.askyesno("Done", f"Character list saved ({n_chars} unique characters).\n\nOpen output folder?"):
            open_folder(out_path.parent)

    # Enables/disables the video screen's frequency buttons based on whether a video has been
    # generated yet, and whether the current language supports character lists.
    def _update_video_freq_buttons(self) -> None:
        has_srt = self._last_video_srt is not None
        self._video_word_freq_btn.config(state="normal" if has_srt else "disabled")
        lang = Language.from_label(self._lang_var.get())
        self._video_char_freq_btn.config(
            state="normal" if has_srt and character_frequency.supports_language(lang) else "disabled"
        )

    # Called when the pipeline succeeds: prompts the user to open the output folder
    def _on_done(self) -> None:
        if messagebox.askyesno("Done", "Processing complete!\n\nOpen the output folder?"):
            open_folder(ROOT / "output" / "final")

    # Called when the video pipeline succeeds: records the generated SRT and prompts to open the output folder
    def _on_video_done(self, srt_path: Path | None) -> None:
        self._last_video_srt = srt_path
        self._update_video_freq_buttons()
        if messagebox.askyesno("Done", "Video processing complete!\n\nOpen the output folder?"):
            open_folder(ROOT / "output" / "final")

    # Re-enables all controls after a pipeline finishes (success or failure)
    def _on_finish(self) -> None:
        self._start_btn.config(state="normal")
        self._video_generate_btn.config(state="normal")
        self._lang_combo.config(state="readonly")
        self._convert_combo.config(state="readonly")
        self._precision_combo.config(state="readonly")
        self._source_combo.config(state="readonly")
        self._mode_combo.config(state="readonly")
        self._voice_combo.config(state="readonly")

    # Deletes all files in the output folder after user confirmation
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
        self._last_video_srt = None
        self._update_video_freq_buttons()
        self._log_panel.write("Output folder cleared.\n")

    # Updates the status label and progress bar (called from the pipeline thread via schedule)
    def _set_status(self, text: str, pct: float) -> None:
        self._status_lbl.config(text=text)
        self._progress["value"] = pct


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
