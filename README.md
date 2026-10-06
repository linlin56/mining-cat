# MiningCat

📖 **Documentation: <https://linlin56.github.io/mining-cat/>**

MiningCat is an all-in-one tool for learning languages through immersion and sentence mining. Read books and comics, watch videos, play games, look up words in your own dictionaries, and turn the sentences you like into flashcards you can export to [Anki](https://apps.ankiweb.net/).

Everything runs locally, in your browser: nothing is sent online.

## What it does

- **Read**: an ebook reader (EPUB, TXT, horizontal or vertical text) and a comic / manga reader whose text is read by OCR.
- **Watch**: a video player for local videos with their subtitles, or YouTube / Instagram / Bilibili links downloaded with their captions.
- **Play**: OCR on a game window (or any window), each line pushed with its screenshot to a page you can mine from.
- **Look up words**: a dictionary popup that reads [Yomitan](https://github.com/yomidevs/yomitan)-format dictionaries (CC-CEDICT, JMdict, Wiktionary…), with character dictionaries and frequency lists.
- **Know where you stand**: words coloured by status (new, learning, known), the share of a text you understand, and the sentences worth mining next (i+1), ranked with your frequency list.
- **Make cards**: a card creator with the word, its reading, definitions, the sentence, its audio, a screenshot and an offline translation. Cards go to Anki through AnkiConnect, or are exported as an `.apkg` file. Your Anki decks keep the word statuses up to date.
- **Create mineable videos**: turn an audiobook and its ebook into `.mp4` videos with accurate subtitles, chapter by chapter. Only the audiobook? Subtitles are generated with Whisper. Only the ebook? The audio is generated with text-to-speech. Videos without subtitles get them transcribed, or read from burned-in subtitles with OCR.
- **Extras**: simplified ↔ traditional Chinese conversion, zhuyin, word frequency lists and Kanji Grid character lists.

## Supported languages

| Language   | Variants                                 |
| ---------- | ---------------------------------------- |
| Mandarin   | Taiwan (traditional), China (simplified) |
| Cantonese  | Hong Kong (traditional)                  |
| Japanese   |                                          |
| Korean     |                                          |
| Vietnamese |                                          |
| English    | United States, United Kingdom            |
| French     |                                          |
| German     |                                          |
| Italian    |                                          |
| Spanish    |                                          |
| Portuguese | Brazil and Portugal voices               |
| Polish     |                                          |

## Getting started

Requirements: Python 3.14, [ffmpeg](https://ffmpeg.org/), a web browser and `make`.

```bash
git clone https://github.com/linlin56/mining-cat.git
cd mining-cat
python3 -m venv .venv
source .venv/bin/activate
make install
make gui
```

The GUI opens at <http://127.0.0.1:5050/>. Pick the language you study, then open the **Converter**, the **Reader**, the **Player** or the **Settings** (dictionaries and Anki). `make reader` and `make player` open the reader and the player directly.

See the [documentation](https://linlin56.github.io/mining-cat/how-to-use/) for each workflow, and the [CLI reference](https://linlin56.github.io/mining-cat/how-to-use/cli/) to use MiningCat from the terminal.

This project is fairly recent: [issues](https://github.com/linlin56/mining-cat/issues) and contributions are very appreciated! See [CONTRIBUTE.md](CONTRIBUTE.md).

## License

MiningCat is free software, released under the [GNU Affero General Public License v3.0 or later](LICENSE) (AGPL-3.0-or-later).

You are free to use, study, modify and redistribute it. If you distribute a modified version, or make it available to users over a network, you must publish its source code under the same license.

MiningCat doesn't provide any book or video. Only use it with content you are allowed to use.
