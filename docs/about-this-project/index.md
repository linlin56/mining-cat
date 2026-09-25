# About this project

MiningCat makes language learning through immersion and sentence mining easier.

There are already great tools that let you create flashcards from videos, books and websites, for example:

- [Yomitan](https://github.com/yomidevs/yomitan): a pop-up dictionary browser extension
- [asbplayer](https://github.com/killergerbah/asbplayer): a video player that works with Yomitan
- [Migaku](https://migaku.com/): a paid all-in-one solution

The goal is not to replace those.
However, they all need good videos with clean subtitles to work. Your favorite video may have none, or you may be reading an ebook alongside its audiobook and wish you could have both in one place. That's what MiningCat is for.

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