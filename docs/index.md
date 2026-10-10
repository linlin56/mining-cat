# MiningCat

MiningCat is an all-in-one tool for learning languages through immersion and sentence mining. Read, watch and play in the language you study, look up words in your own dictionaries, and turn the sentences you like into flashcards you can export to [Anki](https://apps.ankiweb.net/).

Everything runs locally, in your browser: nothing is sent online.

![The reader: words coloured by status, and the dictionary popup on 太陽 with its rank in a frequency list](assets/screenshots/reader-lookup.png)

- **Read** ebooks (EPUB, TXT, horizontal or vertical text) and comics or manga, whose text is read by OCR, in the [reader](how-to-use/reader.md).
- **Watch** local videos with their subtitles, or YouTube, Instagram and Bilibili videos with their captions, in the [player](how-to-use/player.md).
- **Play** a video game: MiningCat reads its dialog boxes with OCR and sends every line, with a screenshot, to a [page you can mine from](how-to-use/video-game.md).
- **Look up words** with a dictionary popup that reads [Yomitan](https://github.com/yomidevs/yomitan)-format dictionaries, and **see where you stand**: words coloured by status, how much of a text you understand, and the sentences worth mining next (i+1). See [Dictionaries & Anki cards](how-to-use/mining.md).
- **Make cards** with the word, its reading, definitions, the sentence, its audio, a screenshot and a translation, sent to Anki or exported as an `.apkg` file. Your Anki decks keep the word statuses up to date.
- **Create mineable videos** from what you have:
    - an audiobook **and** its ebook: MiningCat aligns the book text on the narrator's voice, chapter by chapter;
    - only the audiobook: subtitles are generated with [Whisper](https://github.com/openai/whisper);
    - only the ebook: the audio is generated with text-to-speech;
    - a video without subtitles: MiningCat transcribes it, keeps existing subtitles when there are some, and can even read burned-in subtitles with OCR.

On top of that, MiningCat converts between simplified and traditional Chinese characters, writes zhuyin, and builds frequency lists from what you read and watch.

## Supported languages

| Language   | Variants                                            |
| ---------- | --------------------------------------------------- |
| Mandarin   | Taiwan (traditional), China (simplified)            |
| Cantonese  | Hong Kong (traditional)                             |
| Taigi      | Hanji, Tâi-lô, Pe̍h-ōe-jī ([local speech engines](how-to-use/taigi.md)) |
| Japanese   |                                                     |
| Korean     |                                                     |
| Vietnamese |                                                     |
| Russian    |                                                     |
| English    | United States, United Kingdom                       |
| French     |                                                     |
| German     |                                                     |
| Italian    |                                                     |
| Spanish    |                                                     |
| Portuguese | Brazil and Portugal voices                          |
| Polish     |                                                     |

## Where to go next

<div class="grid cards" markdown>

- **[How to use](how-to-use/index.md)**

    Install MiningCat, then read, watch, play and mine.

- **[How to contribute](how-to-contribute/index.md)**

    Set up a dev environment, run the tests, add a language or a video platform.

- **[About](about-this-project/index.md)**

    Who maintains MiningCat, the projects it's built on, and its license.

</div>

!!! note "Early days"
    This project is fairly recent and has only been tested with a handful of books and videos.
    [Issues](https://github.com/linlin56/mining-cat/issues) and contributions are very appreciated!

## License

MiningCat is free software, released under the [GNU Affero General Public License v3.0 or later](https://github.com/linlin56/mining-cat/blob/main/LICENSE) (AGPL-3.0-or-later).

You are free to use, study, modify and redistribute it. If you distribute a modified version, or make it available to users over a network, you must publish its source code under the same license.
