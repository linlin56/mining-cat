# CLI reference

Everything the GUI does is also available from the terminal. 
I really recommend using the GUI because it's way simpler and battle-tested.
Commands are run from the project root:

```bash
python src/main.py <command> [options]
```

## Audiobook pipeline

Unlike the GUI, the CLI reads its inputs from fixed folders. Put your files there first:

- the ebook (`.epub` or `.txt`) in `sources/ebook/`
- the audio files in `sources/audiobook/`

Then run the steps in order:

```bash
python src/main.py audio             # 1. prepare audio chapters
python src/main.py epub --range 4-9  # 2. extract the book text, one file per chapter
python src/main.py align --language french --model tiny   # 3. align text on audio
python src/main.py export --all --language french         # 4. render the MP4 files
```

Or all at once (with default options): `python src/main.py run --range 4-9`.

### `audio`

Prepares the audio chapters in `output/chapters_audio/`: splits a `.m4b` by chapter markers, or copies the audio files (one per chapter).

| Option      | Description                                        |
| ----------- | -------------------------------------------------- |
| `--dry-run` | Show the detected chapters without extracting them |

### `epub`

Extracts the book text into `output/chapters_text/chapter_001.txt`, `chapter_002.txt`...

| Option               | Description                                    |
| -------------------- | ---------------------------------------------- |
| `--list`             | List the chapters without extracting them      |
| `--range A-B`        | Extract only chapters A to B (e.g. `4-9`)      |
| `--chapters N,M,...` | Extract a manual selection (e.g. `3,4,5`)      |
| `--preview`          | Print a text excerpt for each chapter          |

Use `--list` and `--preview` first to find which chapters match the audiobook.

### `align`

_Standard mode._ Aligns each chapter's text on its audio and writes the subtitles to `output/srt/`.

| Option             | Default       | Description                                                         |
| ------------------ | ------------- | ------------------------------------------------------------------- |
| `--model`          | `tiny`        | Whisper model: `tiny`, `base`, `small`, `medium`, `large`, `turbo`  |
| `--language`       | `mandarin_tw` | See [language ids](#language-ids)                                   |
| `--from N`         |               | Start from chapter N                                                |
| `--only N`         |               | Process only chapter N                                              |

### `transcribe`

_Generate subtitles mode._ Transcribes the audio chapters with Whisper, without an ebook. Same options as `align`.

### `tts`

_Generate audio mode._ Generates the audio of each extracted chapter with edge-tts, along with its subtitles.

| Option       | Default       | Description                                               |
| ------------ | ------------- | --------------------------------------------------------- |
| `--voice`    | _required_    | edge-tts voice name, e.g. `zh-TW-HsiaoChenNeural`         |
| `--language` | `mandarin_tw` | See [language ids](#language-ids)                         |

List the available voices with `edge-tts --list-voices`.

### `convert`

Converts every subtitle file in `output/srt/` between Chinese scripts with OpenCC.

| Option     | Values                  | Description                                                     |
| ---------- | ----------------------- | --------------------------------------------------------------- |
| `--source` | `s`, `tw`               | Source script: `s` = simplified, `tw` = traditional (Taiwan)    |
| `--target` | `s`, `tw`, `t`, `hk`    | Target script: `t` = traditional, `hk` = traditional (Hong Kong) |

### `export`

Renders the final videos into `output/final/chapter_001.mp4`... Each video shows the book and chapter title over the audio, with the subtitles embedded.

| Option       | Default       | Description                                                                 |
| ------------ | ------------- | --------------------------------------------------------------------------- |
| `--chapter N`|               | Export only chapter N                                                       |
| `--all`      |               | Export all chapters                                                         |
| `--language` | `mandarin_tw` | Sets the subtitle language metadata                                         |
| `--preset`   | `ultrafast`   | ffmpeg encoding preset: `ultrafast`, `superfast`, `veryfast`, `faster`, `fast`, `medium` |

### `run`

Runs `audio`, `epub`, `align` and `export --all` in sequence with default options.

| Option        | Description                         |
| ------------- | ----------------------------------- |
| `--range A-B` | Ebook chapter range (e.g. `4-9`)    |

## `video`

Downloads an online video, or uses a local file, and generates its subtitles. See [Videos](video.md) for the details.

```bash
python src/main.py video --url <URL> [options]
python src/main.py video --file <PATH> [options]
```

| Option              | Default       | Description                                                                                  |
| ------------------- | ------------- | -------------------------------------------------------------------------------------------- |
| `--url` / `--file`  | _one required_| Video URL, or path to a local video file                                                     |
| `--model`           | `tiny`        | Whisper model                                                                                |
| `--language`        | `mandarin_tw` | See [language ids](#language-ids)                                                            |
| `--convert-to`      |               | Convert the generated subtitles to `s`, `tw`, `t` or `hk`                                    |
| `--audio-track`     | container default | 0-based index of the audio stream to transcribe, for videos with several dubs            |
| `--ocr`             |               | Read burned-in subtitles with OCR instead of transcribing the audio                          |
| `--ocr-region`      | bottom third  | Subtitle area as `X,Y,W,H` fractions between 0 and 1, e.g. `0,0.75,1,0.25`                   |
| `--ocr-fps`         | `4`           | Frames sampled per second for OCR (2 to 12)                                                  |
| `--app-id`          | `web`         | Instagram only: `X-IG-App-ID` header (`web`, `ios` or a numeric id), if downloads start failing |

## Language ids

| Id             | Language                              |
| -------------- | ------------------------------------- |
| `mandarin_tw`  | Mandarin - Taiwan (Traditional)       |
| `mandarin_cn`  | Mandarin - China (Simplified)         |
| `cantonese_hk` | Cantonese - Hong Kong (Traditional)   |
| `japanese`     | Japanese                              |
| `korean`       | Korean                                |
| `vietnamese`   | Vietnamese                            |
| `english_us`   | English - United States               |
| `english_uk`   | English - United Kingdom              |
| `french`       | French                                |
| `german`       | German                                |
| `italian`      | Italian                               |
| `spanish`      | Spanish                               |
| `portuguese`   | Portuguese                            |
| `polish`       | Polish                                |

## Make shortcuts

The Makefile wraps the most common commands. Variables can be overridden on the command line.

| Command                          | Equivalent                                       |
| -------------------------------- | ------------------------------------------------ |
| `make gui`                       | Launch the GUI                                   |
| `make audio`                     | `audio`                                          |
| `make epub [RANGE=4-9]`          | `epub [--range 4-9]`                             |
| `make align [CHAPTER=1\|all]`    | `align --only 1` (or all chapters)               |
| `make export [CHAPTER=1\|all]`   | `export --chapter 1` (or `--all`)                |
| `make chapter N=5`               | `align` + `export` for chapter 5                 |
| `make chapter1`                  | `align` + `export` for chapter 1                 |
| `make run [RANGE=4-9]`           | `run [--range 4-9]`                              |
| `make video URL=...`             | `video --url ...`                                |
| `make video FILE=...`            | `video --file ...`                               |
| `make clean`                     | Delete generated files in `output/` and `temp/`  |

Available variables and their defaults: `MODEL=tiny`, `LANGUAGE=mandarin_tw`, `PRESET=ultrafast`, `CHAPTER=1`, `APP_ID=web`.

```bash
make align CHAPTER=all MODEL=base LANGUAGE=japanese
make export CHAPTER=all PRESET=superfast LANGUAGE=japanese
make video URL="https://www.instagram.com/reel/xxxxx/" LANGUAGE=korean
```

!!! warning
    `make export` doesn't pass `LANGUAGE`, so the subtitle language metadata defaults to Mandarin. Use `python src/main.py export --all --language <id>` if the metadata matters to your player.
