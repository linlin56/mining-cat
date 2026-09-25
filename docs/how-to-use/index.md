# Getting started
!!! warning
    Currently, there's not executable files for this project. Installation requires to use the terminal.

## Requirements

- **Python** 3.14 (the version used in CI; tested with 3.14.5)
- **ffmpeg**, used to split, convert and render audio and video
    - macOS: `brew install ffmpeg`
    - Debian/Ubuntu: `sudo apt install ffmpeg`
- **Tk bindings for Python** (`tkinter`), needed for the GUI
    - macOS: bundled with the official python.org installer (Homebrew's `python` also needs `brew install python-tk`)
    - Debian/Ubuntu: `sudo apt install python3-tk`
- **make**, to use the shortcuts below (you can also call `python src/main.py` directly, see [CLI reference](cli.md))

Everything else (Whisper, yt-dlp, edge-tts, OpenCC, [owocr](https://pypi.org/project/owocr/)...) is installed by `make install`.

## Installation

```bash
git clone https://github.com/linlin56/mining-cat.git
cd mining-cat

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install the dependencies
make install
```

!!! tip
    The Makefile automatically uses `.venv/bin/python3` when it exists, so `make` commands work even if you forget to activate the environment.

## Launch the GUI

```bash
make gui
```

The window header has three settings shared by every workflow:

| Setting        | What it does                                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Source**     | `Audiobook / Ebook` or `Video`. Picks which screen you're working with.                                                             |
| **Language**   | The original language of your input files. It drives transcription, punctuation fixes, TTS voices and subtitle metadata.          |
| **Convert to** | Only for Chinese variants: converts subtitles between simplified and traditional characters (e.g. read a mainland book in traditional). |

Then pick your workflow:

- [Audiobooks & ebooks](audiobook-ebook.md): one video per chapter, from a book and/or its audiobook.
- [Videos](video.md): subtitles for a YouTube, Instagram or Bilibili video, or a video file on your computer.

When you're done, the videos are in `output/final/`. Open them in your player, in asbplayer or Migaku and start mining!

## Accepted inputs

| Input      | Formats                                                      |
| ---------- | ------------------------------------------------------------ |
| Ebook      | `.epub` (recommended), `.txt` (one or several files)         |
| Audiobook  | `.m4b` (split with its chapter markers), `.mp3`, `.m4a`, `.aac`, `.ogg`, `.wav`, `.flac`, `.opus` (one file per chapter) |
| Video      | A URL from a [supported platform](video.md#from-the-web), or any local video file ffmpeg can read |

See [Files and folders](files.md) for where everything ends up.
