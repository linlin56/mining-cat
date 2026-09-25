# Frequency lists

Frequency lists help you decide what to study: the most frequent words of a book are the ones worth learning first.

They're available:

- in **Standard** and **Generate audio** modes, once an ebook is loaded and chapters are selected (the list covers the selected chapters);
- for **Videos**, once a video has been processed (computed from the Whisper transcript).

Files are saved in `output/frequency/`.

## Word frequency

Generates a `.csv` file with each unique word and its number of occurrences, sorted from most to least frequent. Works for all languages.

Languages written without spaces are segmented with a dedicated tokenizer: jieba for Chinese, Janome for Japanese.

## Character list

Generates a `.json` file compatible with [Kanji Grid](https://github.com/Kuuuube/kanjigrid), grouping characters by frequency rank (top 1k, 2k, etc.). Import it in Kanji Grid to see which characters of the book you already know.