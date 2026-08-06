# AudiobookMiner

## Description

This project is meant to create _mineable_ videos, out of audiobooks, ebooks, and/or online videos (Instagram Reels, YouTube...), so that you can use it for language learning (with tools like Migaku or asbplayer).  
The GUI lets you convert characters if needed.

I will make it more polyvalent in the future and support more languages and platforms.
Contributions and issues are very appreciated!

## Supported languages

- Mandarin (Taiwan, traditional characters)
- Mandarin (China, simplified characters)
- Japanese
- French
- English (American and British supported)
- Italian
- Spanish
- Polish
- Korean
- German
- Portuguese (Brazil and Portugal voices)
- Vietnamese
- Cantonese (Hong Kong, traditional characters)

### How to use it

This project is fairly recent and has only been tested with a handful of books.

#### Requirements

- Python (tested with 3.14.5)
- `venv` (bundled with Python) to create an isolated environment
- Tk bindings for Python (`tkinter`), needed for the GUI :
  - Debian/Ubuntu : `sudo apt install python3-tk`
  - macOS : bundled with the official python.org installer (Homebrew's `python` also needs `brew install python-tk`)
- [owocr](https://pypi.org/project/owocr/) for hardsubs OCR (video mode) — installed automatically by `make install`, no separate step needed

The simplest way to use :

1. Create and activate a virtual environment, e.g. `python3 -m venv .venv`
2. Run `make install`
3. Run `make gui`
4. Follow the instructions.

You can use an ebook in .epub and .txt format, and/or audiobook in .mp3 or .m4b, and/or a video downloaded from the web (see [Video from Web](#video-from-web)).

## Language options

- Language : select the input's files original language
- Convert to : (available with mandarin) converts simplified <-> traditional characters if needed

## Source

The GUI has a **Source** dropdown that picks which screen you're working with:

- **Audiobook / Ebook** : the original workflow described below (Modes, Precision, ebook/audio panels, frequency lists).
- **Video** : download a video from a supported platform, or provide your own local video file, and generate mineable subtitles for it. See [Video](#video).

The rest of the header (Language, Convert to, Precision) applies to both screens.

## Modes

_Only applies to the "Audiobook / Ebook" source._

There are 3 modes in the GUI :

#### Standard mode

- Provide an ebook and its corresponding audio files.
- You will get .mp4 videos (one per chapter) with the audiobook's audio and subtitles made from the ebook.

#### Generate subtitles mode

- Provide audio files.
- You will get .mp4 videos (one per chapter) with the audiobook's audio and generated subtitles.
  This mode gives less accurate subtitles, but it's useful if you don't have the ebook.

#### Generate audio mode

- Provide the ebook file.
- You will get .mp4 videos (one per chapter) generate audio (TTS) with subtitles made from the ebook.
  This mode generates audio, which is way less natural than an actual narrator, but it's great if you don't have the audio files.

## Video

_Select "Video" in the Source dropdown._

Get an .mp4 with generated subtitles, saved in `output/final/`, from either an online video or a video already on your computer.

#### Input source

- **From web** : pick the **Target website** (currently informational - the actual platform is auto-detected from the URL) and paste the video **URL**.
  - **Instagram** : Reels
  - **YouTube** : regular videos and Shorts
  - **Bilibili** : regular videos
  - More to come :)
- **Local file** : pick a video file already on your computer, just like you'd provide an ebook.

#### How it works

1. Pick **From web** or **Local file** and provide the video.
2. If a local file has more than one audio track (e.g. multiple dubs), an **Audio track** dropdown appears - pick the one matching the selected Language.
3. Click **Generate From Source**.
4. The video is loaded, its audio is transcribed with Whisper (using the selected Language, Precision, and audio track) to build a `_whisper.srt` subtitle track.
5. If the video already has subtitles, they're kept alongside the Whisper track as a `_source.srt` :
   - **YouTube** : manual or auto-generated captions in the target language are downloaded alongside the video.
   - **Local file** : a same-stem sidecar `.srt` next to the video (e.g. `movie.mp4` + `movie.en.srt`) is reused, or failing that a text-based subtitle track already muxed into the video container is extracted (bitmap subtitle formats like PGS/VobSub can't be extracted this way).
   - Instagram and Bilibili don't expose usable platform subtitles, so their videos only ever get the Whisper track.
   - The final video ends up with two subtitle tracks (labelled "Source" and "Whisper" in players like VLC) when both are available, or just "Whisper" otherwise.
6. Subtitle files live in `output/srt/`, same as the audiobook workflow, so **Convert to** and both **Frequency lists** buttons work the same way (computed from the Whisper transcript).

#### CLI

```
python src/main.py video --url <URL> [--model tiny] [--language mandarin_tw] [--convert-to s]
# or
python src/main.py video --file <PATH> [--model tiny] [--language mandarin_tw] [--convert-to s] [--audio-track 1]
# or
make video URL="<URL>"
# or
make video FILE="<PATH>"
```

Instagram-only: `--app-id` overrides the X-IG-App-ID header (`web` by default, or `ios`/a numeric id) if downloads start failing.

`--audio-track` picks which 0-based audio stream to transcribe when the video has several (useful for local files with multiple dubs); omit it to use the container's default audio stream.

## Precision

If using standard mode, generate subtitles mode, or Video from Web, you will also have the precision option.  
The subtitles timing are generated using Whisper. this allows you to select which Whisper model you want to use.

- Base (default) : recommended for most usages
- Tiny : recommended for standard mode, should be a little bit faster
- Small, Medium and Large : only recommended for "generate subtitles" mode or Video from Web, as this takes longer to generate. Should give better subtitles (useless in standard mode because we use the ebook.)

## Frequency lists

Available in Standard and Generate audio modes (requires an ebook to be loaded with chapters selected), and in Video from Web (computed from the generated Whisper transcript once a video has been processed).

- **Word frequency** : generates a `.csv` file with each unique word and its occurrence count, sorted by frequency. Works for all languages.
- **Character list** : generates a `.json` file compatible with [Kanji Grid](https://github.com/Kuuuube/kanjigrid), grouping characters by frequency rank (top 1k, 2k, etc.). Only available for Mandarin and Japanese.

Output files are saved in `output/frequency/`.

## Chapter selection

You can select specific chapters to target.
this is useful if you ebook doesn't match exactly with the audio, for example if it has an table of content of a preface.
In the UI, just select (highlight) chapters.  
In the CLI, use the "range" option.  
This is only available with .epub format
