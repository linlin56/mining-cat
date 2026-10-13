# Getting started
!!! warning
    Currently, there's not executable files for this project. Installation requires to use the terminal.

## Requirements

- **Python** 3.14 (the version used in CI; tested with 3.14.5)
- **ffmpeg**, used to split, convert and render audio and video
    - macOS: `brew install ffmpeg`
    - Debian/Ubuntu: `sudo apt install ffmpeg`
    - Windows: see [Installation on Windows](#installation-on-windows)
- **A web browser**: the GUI is a local web page (nothing is sent online)
- **make**, to use the shortcuts below (you can also call `python -m miningcat` directly, see [CLI reference](cli.md))

Everything else (Whisper, yt-dlp, edge-tts, OpenCC, [owocr](https://pypi.org/project/owocr/)...) is installed by `make install`.
The local voice reading the sentences and the books, [OmniVoice](https://github.com/k2-fsa/OmniVoice), is large: install
it from Settings › Voice (Install OmniVoice), or with `make install-omnivoice` (about 4 GB with its model, in its own
environment `.venv-omnivoice`). The first use can be long: the model is put in the cache, and each language's voice is made up once.

![Settings › Voice: edge-tts or OmniVoice, its install and its quality](../assets/screenshots/settings-voice.png) Settings › Voice also sets its quality. edge-tts is used by default (faster, but online): once OmniVoice is installed,
OmniVoice takes over when Edge fails (a message tells you), and reads everything if you untick "Use edge-tts when available".

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

!!! note "macOS 26.0 to 26.2"
    If you're on macOS 26.0, 26.1 or 26.2 and Python installed with Homebrew doesn't work (`Symbol not found: _XML_SetAllocTrackerActivationThreshold`),
    it's a [Homebrew issue](https://github.com/Homebrew/homebrew-core/issues/277330). Install Python another way, then recreate the environment:

    - the installer from [python.org](https://www.python.org/downloads/macos/), then `rm -rf .venv && python3.14 -m venv .venv`
    - or [uv](https://docs.astral.sh/uv/):

        ```bash
        uv python install 3.14
        rm -rf .venv && uv venv --python 3.14 --seed .venv
        ```

    Then `make install` as usual.

### Installation on Windows

Windows doesn't come with `make`, Python 3.14 or ffmpeg. The simplest way to get them is [Chocolatey](https://chocolatey.org/install), a package manager for Windows.

1. Open **PowerShell as administrator** (right-click on PowerShell › *Run as administrator*), and install Chocolatey by following [its guide](https://chocolatey.org/install#individual).
2. In the same window, install the tools:

    ```powershell
    choco install git make python314 ffmpeg -y
    ```

3. Close PowerShell and open a new one, **not** as administrator this time (the new window sees the newly installed tools). Then:

    ```powershell
    git clone https://github.com/linlin56/mining-cat.git
    cd mining-cat

    make venv       # creates .venv with Python 3.14
    make install    # installs the dependencies in .venv
    make gui
    ```

The Makefile uses `.venv\Scripts\python.exe` when it exists: no need to activate the environment.

!!! tip "Without make"
    Every `make` command is a shortcut for a Python command (see [CLI reference](cli.md)). In PowerShell, from the `mining-cat` folder:

    ```powershell
    py -3.14 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    .venv\Scripts\python.exe -m pip install --no-deps "owocr>=1.26.8"

    $env:PYTHONPATH = "src"
    .venv\Scripts\python.exe -m miningcat.interfaces.web --port 5050
    ```

    Don't forget the `owocr` line: it isn't in `requirements.txt` (it's installed apart, without its dependencies), and the [video game](video-game.md) OCR needs it. `$env:PYTHONPATH` only lasts as long as the PowerShell window: set it again in a new one.

## Launch the GUI

```bash
make gui
```

MiningCat starts a small local server and opens the GUI in your browser at <http://127.0.0.1:5050/>. Keep the terminal open while you use it, and press `Ctrl+C` there to stop it. Use `make gui PORT=8080` if the port is already taken.

### Choose the language you study

The home page first asks which language you study. Every screen then only shows what belongs to it: the converter's variants, the books of the reader, the videos of the player, and in the settings the dictionaries, words, Anki decks and cards of that language. Change it at any time with the language badge in the header of every page, which brings you back to the home page.

![The home page asks which language you study](../assets/screenshots/home-language-picker.png)

From the home page, open the **Converter**, the [Reader](reader.md), the [Player](player.md) or the **Settings**.
When Anki is open (with AnkiConnect), the home page also shows, under the screens, where your reviews stand today
(not started, cards left, or done), your streak of days in a row with reviews, and a heatmap of your reviews over the
last year. Only the decks linked to the language you study count (with their subdecks): the deck its cards go
to and the decks synced with its words, in **Settings › Anki**. Your other decks (maths...) don't.

![The home page, once the language is chosen: the screens, then today's Anki reviews, the streak and the heatmap](../assets/screenshots/home-hub.png)

The **Settings** have a tab per topic: **Dictionaries** (import a dictionary or a frequency list), **Words**, **Anki**, **Translation**, **Cards** (the cards waiting for Anki) and **User preferences**: the theme (light, dark, or your system's), the highlight colours (with palettes for colour blindness) and the Discord status. The moon button in the header of every page also switches between light and dark.

![Settings › User preferences: theme, highlight colours and Discord status](../assets/screenshots/settings-preferences.png)

While MiningCat runs, your Discord profile shows what you do in it ("Reading a book", "Watching a video", "Playing" and the [source name](video-game.md) of a game...) and the language you study, with your Anki streak once the home page got it ("Japanese · 🔥 12-day streak"), if the Discord app is open on the same computer. Turn it off in **Settings › User preferences › Discord**.

You can drag and drop files on the audio, book and video panels. The files you pick are copied into the project's `sources/` folder, like before.

The converter's header has three settings shared by every workflow:

| Setting        | What it does                                                                                                                        |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Source**     | `Audiobook / Ebook`, `Video` or `Video game / Screen share`. Picks which screen you're working with.                                |
| **Variant**    | Only when the language studied has several (Mandarin: Taiwan or China, English: US or UK). It drives transcription, punctuation fixes, TTS voices and subtitle metadata. |
| **Convert to** | Only for Chinese variants: converts subtitles between simplified and traditional characters (e.g. read a mainland book in traditional). |

Then pick your workflow:

- [Audiobooks & ebooks](audiobook-ebook.md): one video per chapter, from a book and/or its audiobook.
- [Videos](video.md): subtitles for a YouTube, Instagram or Bilibili video, or a video file on your computer.
- [Video games & screen share](video-game.md): OCR the text of a game window, and mine it from a web page.

When you're done, the videos are in `output/final/`. Open them in MiningCat's [video player](player.md), or in any player you like, and start mining!

## Accepted inputs

| Input      | Formats                                                      |
| ---------- | ------------------------------------------------------------ |
| Ebook      | `.epub` (recommended), `.txt` (one or several files)         |
| Audiobook  | `.m4b` (split with its chapter markers), `.mp3`, `.m4a`, `.aac`, `.ogg`, `.wav`, `.flac`, `.opus` (one file per chapter) |
| Video      | A URL from a [supported platform](video.md#from-the-web), or any local video file ffmpeg can read |
| Video game | Any window on screen ([Linux and macOS](video-game.md#supported-systems)) |

See [Files and folders](files.md) for where everything ends up.
