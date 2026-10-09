# MiningCat 🐱

<img src="docs/assets/logo/miningcat.png" alt="MiningCat logo: an orange cat with a miner's helmet and a pickaxe" width="160">

📖 **Documentation: <https://linlin56.github.io/mining-cat/>**

MiningCat is a free and open source, all-in-one tool for learning languages through immersion and sentence mining. Read, watch and play in the language you study, look up words in your own dictionaries, and turn the sentences you like into Anki flashcards.

> ℹ️ Support is experimental for some languages. [Issues](https://github.com/linlin56/mining-cat/issues) are very welcome!

## Features

- 📚 **Read** EPUB, TXT, HTML, Markdown, comics and manga (horizontal or vertical text, furigana, saved progress), or paste any text in the Clipboard page.
- 🎬 **Watch** local videos, or YouTube, Instagram (Reels) and Bilibili videos, in a player made for mining.
- 🎮 **Play**: dialog boxes of a game (or any window) are read with OCR and sent, with a screenshot, to a page you can mine from.
- 🔎 **Look up** words with a popup that reads [Yomitan](https://github.com/yomidevs/yomitan)-format dictionaries, with conjugation handling, pitch accent, audio and frequency ranks.
- 📈 **Track** your progress: words coloured by status, comprehension of each text, and the **i+1** sentences worth mining next.
- 🃏 **Make cards** (word, reading, definitions, sentence, audio, image, translation) sent to Anki through AnkiConnect, or exported as `.apkg`. Your Anki decks keep your word statuses up to date.
- 🎞️ **Create mineable videos** (`.mp4` + `.srt`) from an audiobook and its ebook, an audiobook alone, an ebook alone (text-to-speech), or a video without subtitles (transcription, or OCR of burned-in subtitles).
- 🈶 **Chinese tools**: simplified ⇄ traditional conversion, zhuyin / pinyin, context-aware readings.
- 🇹🇼 **Taigi tools**: Hanji ⇄ Tâi-lô ⇄ Pe̍h-ōe-jī conversion, and local speech engines for Taigi (`make install-taigi`).

**Languages:** Mandarin (Taiwan, traditional / China, simplified), Cantonese (Hong Kong), Taiwanese Hokkien (Taigi: Hanji, Tâi-lô and Pe̍h-ōe-jī), Japanese, Korean, Vietnamese, English (US / UK), French, German, Italian, Spanish, Portuguese (Brazil / Portugal), Polish.

## Under the hood

MiningCat chains several speech and NLP components into one local, multilingual pipeline:

| Task | Components |
| --- | --- |
| Speech recognition | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), with selectable model sizes (tiny to large / turbo); [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) for Taigi |
| Forced alignment of a book's text on its audiobook | [stable-ts](https://github.com/jianfch/stable-ts) (Whisper-based); Meta's MMS aligner on the romanized text for Taigi |
| Speech synthesis | [edge-tts](https://github.com/rany2/edge-tts); Meta's [MMS-TTS](https://huggingface.co/facebook/mms-tts-nan) (local) for Taigi |
| OCR (hardsubs, games, manga) | Apple Vision / Live Text on macOS, [EasyOCR](https://github.com/JaidedAI/EasyOCR) and [owocr](https://github.com/AuroraWright/owocr) elsewhere |
| Offline machine translation of sentences | [Argos Translate](https://github.com/argosopentech/argos-translate) |
| Word segmentation | Longest dictionary match, [jieba](https://github.com/fxsjy/jieba) and [Janome](https://github.com/mocobeta/janome) for frequency lists |
| Morphology | Deconjugation (Japanese, Korean, French, Spanish...), Mandarin readings chosen from the context |
| Learner modelling | Word statuses synced from Anki (card maturity), comprehension rate, i+1 recommendation bounded by a frequency list |
| Chinese script conversion | [OpenCC](https://github.com/BYVoid/OpenCC) |
| Taigi writing systems | Hanji readings with [taibun](https://github.com/andreihar/taibun), Tâi-lô ⇄ Pe̍h-ōe-jī syllable by syllable |

It is a Python project with a local web interface, tested on Linux, macOS and Windows, with a test suite and a CI that requires at least 80% coverage.

## Getting started

> There are currently no executable files: installation requires the terminal.

**Requirements:** Python 3.14 (tested with 3.14.5), [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` / `sudo apt install ffmpeg`), a web browser, and `make`.

```bash
git clone https://github.com/linlin56/mining-cat.git
cd mining-cat

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

make install                   # installs everything else (Whisper, yt-dlp, OpenCC, owocr...)
make gui                       # opens http://127.0.0.1:5050/ in your browser
```

Keep the terminal open while you use MiningCat, and press `Ctrl+C` to stop it (`make gui PORT=8080` if the port is taken). The home page asks which language you study, then gives you the Converter, the Reader, the Player, the Clipboard and the Settings.

Then import your dictionaries and connect Anki in *Settings*, add a book or a video, and click a word to start mining. The full guides (audiobooks & ebooks, videos, video games, reader, player, dictionaries & Anki cards, CLI) are in the [documentation](https://linlin56.github.io/mining-cat/how-to-use/).

## Contributing

Bug reports, language proofreading, new languages, new video platforms, capture backends for other systems and doc fixes are all very welcome. See [CONTRIBUTE.md](CONTRIBUTE.md) and the [contributor guide](https://linlin56.github.io/mining-cat/how-to-contribute/).

## License

MiningCat is free software, released under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later). If you distribute a modified version, or make it available to users over a network, you must publish its source code under the same license.

The MiningCat logo ([docs/assets/logo/](docs/assets/logo/)) is © linlin56, under the [CC BY-SA 4.0](docs/assets/logo/LICENSE.md) license. The name and the logo stay the identity of this project: a fork must use its own.

MiningCat doesn't provide any book or video. Only use it with content you are allowed to use.