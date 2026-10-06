# About this project

MiningCat makes language learning through immersion and sentence mining easier, in one free and open source tool that runs on your computer.

Sentence mining needs a lot of pieces: content with clean subtitles, a reader, a video player, dictionaries, a way to know which words you already know, and flashcards. MiningCat brings them together: it reads your books, comics, videos and games, looks words up in your dictionaries, tells you which sentences are worth mining, and sends the cards to [Anki](https://apps.ankiweb.net/). And when your favorite video has no subtitles, or your ebook and its audiobook live apart, it makes a mineable video out of them.

It started as a personal tool, a handful of scripts to feed my own sentence mining. Then it kept growing, and I realized it could be useful to others: many sentence miners follow the same workflow, each with their own pile of messy scripts. So why not build a clean version and share it?

## Maintainer

MiningCat is maintained by [linlin56](https://github.com/linlin56).
I'm a French developer who likes learning languages.
I mostly use this tool with Mandarin Chinese (Taiwan) and I work on it in my free time.
Don't hesitate to [open an issue](https://github.com/linlin56/mining-cat/issues) when something doesn't work.

## Contributors

Thanks to everyone who reported bugs, proofread a language or sent a pull request! The full list is on the [contributors page](https://github.com/linlin56/mining-cat/graphs/contributors).

Want to join them? See [How to contribute](../how-to-contribute/index.md).

## Built with

MiningCat relies on great open source projects:

| Project                                                                   | Used for                                              |
| ------------------------------------------------------------------------- | ----------------------------------------------------- |
| [ffmpeg](https://ffmpeg.org/)                                             | Splitting, converting and rendering audio and video   |
| [stable-ts](https://github.com/jianfch/stable-ts) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Transcription and alignment of the book text on the audio |
| [edge-tts](https://github.com/rany2/edge-tts)                             | Text-to-speech, when there is no audiobook            |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp)                                | Downloading online videos                             |
| [owocr](https://github.com/AuroraWright/owocr) and [EasyOCR](https://github.com/JaidedAI/EasyOCR) | Reading burned-in subtitles                |
| [EbookLib](https://github.com/aerkalov/ebooklib)                          | Reading `.epub` files                                 |
| [OpenCC](https://github.com/BYVoid/OpenCC)                                | Simplified / traditional Chinese conversion           |
| [jieba](https://github.com/fxsjy/jieba) and [Janome](https://github.com/mocobeta/janome) | Word segmentation for Chinese and Japanese frequency lists |
| [Zensical](https://zensical.org/)                                         | This documentation                                    |

## License

MiningCat is free software, released under the [GNU Affero General Public License v3.0 or later](https://github.com/linlin56/mining-cat/blob/main/LICENSE) (AGPL-3.0-or-later).

MiningCat doesn't provide any book or video. Only use it with content you are allowed to use.

## Why this name?
- "Mining" comes from sentence mining.
- "Cat" is because cats are cool.