# Files and folders

MiningCat works inside the project folder. Everything it generates goes to `output/`, which is ignored by git.

```text
mining-cat/
├── sources/                 # your input files (ignored by git)
│   ├── ebook/               #   the .epub or .txt file(s)
│   ├── audiobook/           #   the audio file(s)
│   └── game_ocr.json        #   the video game window and areas you selected
└── output/
    ├── chapters_audio/      # one audio file per chapter
    ├── chapters_text/       # one text file per chapter (chapter_001.txt...)
    ├── srt/                 # generated subtitles (.srt)
    ├── videos/              # downloaded online videos
    ├── frequency/           # word frequency (.csv) and character lists (.json)
    ├── temp/                # intermediate files (chapter metadata, OCR frames...)
    └── final/               # The videos you want
library/                     # the reader's books, the player's videos, dictionaries and cards (ignored by git)
├── books/                   #   one folder per book
├── videos/                  #   one folder per video: the file, its subtitles, your position
└── miningcat.db             #   dictionaries, word statuses and cards
user/                        # your own settings (ignored by git)
└── user-config.json         #   Settings › User preferences: theme, highlight colors
```

When you pick files in the GUI, they're copied into `sources/` for you. With the [CLI](cli.md), put them there yourself.

!!! warning "Start from a clean slate"
    Each run overwrites the files of the previous one. Move the videos you want to keep out of `output/final/` before processing another book, and run `make clean` to delete everything generated.

!!! note "Copyright"
    `sources/` is ignored by git so that copyrighted books and audiobooks never end up in the repository. Don't commit them!
