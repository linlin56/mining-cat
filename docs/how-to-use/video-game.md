# Video games & screen share

Select **Video game / Screen share** in the **Source** dropdown to mine sentences from anything displayed in a window: a video game, a visual novel, a video call, a website...

MiningCat watches a window, reads its text with OCR, and pushes the **screenshot + text** to a local web page. Open that page next to your game, and mine the sentences from your browser with Migaku, Yomitan or any other browser extension.

Nothing is recorded in `output/`: everything lives in the page, while the capture runs.

## Supported systems

Window capture works very differently from one OS to another, so MiningCat picks the right implementation for yours automatically. The one in use is shown on the **Capture** line of the panel.

| System | Capture | Status |
| ------ | ------- | ------ |
| **Linux** | Desktop portal (ScreenCast) + PipeWire | Tested on Ubuntu, GNOME, Wayland |
| **macOS** | ScreenCaptureKit (macOS 14 or later) | Tested on macOS 15 |

Windows isn't supported yet (you can [help](../how-to-contribute/add-capture-backend.md)!).

### Linux setup

The capture goes through GNOME's screen sharing portal, which needs a few system packages:

```bash
sudo apt install python3-gi gir1.2-gst-plugins-base-1.0 gstreamer1.0-pipewire
```

These are system Python packages: your virtual environment must be able to see them. Create it with `--system-site-packages`:

```bash
python3 -m venv --system-site-packages .venv
make install
```

!!! info "Why the portal?"
    On GNOME/Wayland, classic screenshot tools (`grim`, X11 capture through Xwayland...) either don't work or return black images. The ScreenCast portal is the only reliable way, and it can remember your choice: GNOME asks you which window to share **once**, then MiningCat reopens it without any popup.

### macOS setup

The app you launch MiningCat from (Terminal, iTerm2, VS Code...) needs the **Screen Recording** permission:

1. The first time you click **Select window…**, macOS asks for the permission.
2. Open **System Settings > Privacy & Security > Screen & System Audio Recording** and enable that app.
3. Quit and reopen that app (the permission only applies after a restart), then launch MiningCat again.

The [capture key](#capture-key-or-continuous-capture) also needs the **Input Monitoring** permission for the same app (**System Settings > Privacy & Security > Input Monitoring**). macOS asks for it the first time you click **Start**.

## In the GUI

1. Pick the **Language** of the game (and **Convert to**, for Chinese).
2. Click **Select window…** and pick the game window:
    - **Linux**: GNOME's sharing dialog opens, pick the window there.
    - **macOS**: MiningCat lists the open windows. The game must be open and not minimized.
3. Click **Select window's full size (for screenshot)…** and draw a box around the part of the window you want to see in the page. It's pre-selected on the whole capture.
    - On **Linux**, the portal captures a screen-sized image with the window pasted on a black background: draw the box around the window's edges.
    - On **macOS**, the capture already is the window: keep it as is, or leave out the title bar or black borders.
4. Click **Select text area (for OCR)…** and draw a box around the game's dialog box, where the text appears. It's pre-selected on the whole screenshot area, and **Reset to bottom third** is a good start for most games. Only this part is read by OCR, which makes it faster and avoids reading menus or the HUD.
5. Pick the **Capture key** (`F9` by default), or check **Continuous capture** (see [below](#capture-key-or-continuous-capture)).
6. Click **Start**. The page opens in your browser (or click **Open page**).
7. Play, and press the capture key on each line you want to mine! Click **Stop** when you're done.

The window, the areas and the capture mode are remembered for next time, in `sources/game_ocr.json`. Selecting a new window resets the areas, and selecting a new screenshot area resets the text area (it's relative to the screenshot area).

!!! tip "Moving or resizing the window"
    Areas are stored as fractions of the window, so moving the window is fine, and resizing it keeps working as long as the game layout scales with it.

## Capture key or continuous capture

By default, MiningCat captures when you press the **capture key** (`F9`, or any key from `F1` to `F12`), even while the game is focused. The key still reaches the game.

- **macOS**: MiningCat listens to the key itself. It needs the Input Monitoring permission (see [macOS setup](#macos-setup)). On a Mac keyboard, `F1`-`F12` usually control the brightness, the volume... : press **fn** with the key, or enable **System Settings > Keyboard > Keyboard Shortcuts > Function Keys > Use F1, F2, etc. keys as standard function keys**.
- **Linux (GNOME)**: on Wayland, apps can't listen to the keyboard globally. While the capture runs, MiningCat registers a GNOME custom shortcut (named "MiningCat capture", visible in Settings > Keyboard) that sends the capture request, and removes it when you click **Stop**. Pick a key that isn't already used by another shortcut.

Check **Continuous capture** to capture without pressing anything (the capture key is then greyed out): MiningCat looks at the text area twice per second, and runs OCR when it changed. Games often draw text letter by letter, so it waits until the text area stops changing before reading it, to avoid half sentences. It works best when nothing moves behind the text.

In both modes, a capture is only pushed to the page when the text differs from the previous one, and contains characters of the selected language (e.g. at least a Chinese character for Mandarin).

You can also capture at any time with the **camera button** at the top of the page, or with an HTTP request (e.g. from your own shortcut tool, or on a desktop where the capture key isn't supported):

```bash
curl -X POST http://127.0.0.1:6677/capture
```

## The page

Each capture shows the time, the time it took, the screenshot (dimmed until you hover it) and the text in a large font, ready to be mined.

- **copy image**: copies the screenshot to the clipboard, to paste it in your flashcard.
- **Camera button**: capture now.
- **Bin button**: clear the history, in every open tab.

The page keeps the history while the capture runs: reloading it, or opening it in another tab, replays the last 20 captures.

## OCR

OCR is the same as for [burned-in subtitles](video.md#burned-in-subtitles-ocr): Apple Vision on macOS, EasyOCR elsewhere, in the selected language.

The lines of the dialog box are joined back together, since games wrap long sentences: without spaces for Chinese, Japanese and Cantonese, with spaces for other languages. **Convert to** converts Chinese characters, like for subtitles.

## From the terminal

```bash
python src/main.py game setup                       # pick the window, then draw both areas
python src/main.py game serve --language japanese   # start capturing (F9), Ctrl+C to stop
python src/main.py game serve --hotkey F2           # another capture key
python src/main.py game serve --continuous          # continuous capture instead of the key
```

Or with make: `make game-setup`, then `make game LANGUAGE=japanese HOTKEY=F9`.

On macOS, `game setup` lists the windows and asks for a number, or use `--window` to pick the first window whose app name or title contains some text:

```bash
python src/main.py game setup --window Ryujinx
```

See the [CLI reference](cli.md#game) for all options.

## Troubleshooting

- **"MiningCat needs the Screen Recording permission"** (macOS): see [macOS setup](#macos-setup). If you already enabled it, make sure you restarted the app you launch MiningCat from, and that it's the right one (e.g. VS Code, if you run `make gui` from its terminal).
- **"Window not found"** (macOS): the game was closed or minimized. Open it again: MiningCat finds it back by its app name and title. If its title changed, click **Select window…** again.
- **"The permission may have been revoked"** (Linux): GNOME forgot the window you shared (e.g. after restarting the game). Click **Select window…** again.
- **Nothing shows up in the page**: check the log in the GUI. "no text detected" usually means the text area is wrong (select it again, a bit larger), or the selected **Language** doesn't match the game.
- **The capture key does nothing**: check the log. On macOS, grant the Input Monitoring permission and restart the app you launch MiningCat from, and press **fn** with the key. On GNOME, make sure no other shortcut uses the same key. The page's camera button always works.
- **"Address already in use"**: another capture is already running (maybe from a terminal). Stop it first. From the terminal, you can also use another port with `--port`.
