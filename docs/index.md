# MiningCat

MiningCat turns **audiobooks**, **ebooks** and **online or local videos** into _mineable_ videos: `.mp4` files with accurate, embedded subtitles that you can use with language-learning tools like [Migaku](https://migaku.com/) or [asbplayer](https://github.com/killergerbah/asbplayer).

- Got an audiobook **and** its ebook? MiningCat aligns the book text on the narrator's voice, chapter by chapter.
- Only the audiobook? Subtitles are generated with [Whisper](https://github.com/openai/whisper).
- Only the ebook? The audio is generated with text-to-speech.
- A YouTube video, an Instagram Reel, a movie on your disk? MiningCat transcribes it, keeps existing subtitles when there are some, and can even read burned-in subtitles with OCR.
- Playing a video game? MiningCat reads its dialog boxes with OCR and sends every line, with a screenshot, to a web page you can mine from.

On top of that, MiningCat can convert between simplified and traditional Chinese characters and build frequency lists from what you're watching.

## Supported languages

| Language   | Variants                                            |
| ---------- | --------------------------------------------------- |
| Mandarin   | Taiwan (traditional), China (simplified)            |
| Cantonese  | Hong Kong (traditional)                             |
| Japanese   |                                                     |
| Korean     |                                                     |
| Vietnamese |                                                     |
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

    Install MiningCat and create your first mineable video.

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
