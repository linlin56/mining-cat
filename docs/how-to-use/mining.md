# Dictionaries & Anki cards

MiningCat has its own dictionary popup and card creator, so you don't need to install Yomitan. Everything is set up in **Settings** (link at the top of the converter and the library, or <http://127.0.0.1:5050/settings/>).

## 1. Import dictionaries

Settings › **Dictionaries** › *Choose a .zip…*

MiningCat reads dictionaries in [Yomitan's format](https://github.com/yomidevs/yomitan), so the dictionaries made for Yomitan work as they are: for example [CC-CEDICT](https://github.com/MarvNC/cc-cedict-yomitan/releases) (Mandarin, also in a zhuyin version), words.hk (Cantonese), [JMdict](https://github.com/yomidevs/jmdict-yomitan/releases) (Japanese), [Wiktionary dictionaries](https://github.com/yomidevs/kaikki-to-yomitan) (Korean and many more), and frequency lists.

Character dictionaries work too: KANJIDIC (Japanese) or CC-CEDICT Hanzi (Chinese). The popup then has a **Characters** section under each word, with the readings and meanings of each kanji / hanzi.

- The language is detected from the dictionary's words. If it can't be, choose it in the list before importing.
- Results are shown in the order of the list: use ↑ ↓ to change it. Untick a dictionary to hide it without deleting it.
- When you've imported a frequency list, more frequent words come first in the results.

Dictionaries are stored in `library/miningcat.db`, with your words and cards.

## 2. Look up words in the reader

Click a word in the reader. The popup shows:

- the word, its reading, and how it was conjugated when you clicked an inflected form (Japanese, Korean, French, Spanish…: 泣いていた gives 泣く « -て « -いる « -た, 먹었어요 gives 먹다 « -았/었 « -아/어요);
- the definitions of every dictionary;
- the word's **status**: new, learning, known or ignored. Click to change it;
- its pitch accent (Japanese, with a pitch accent dictionary: たべꜜる [2]) or IPA, and its frequency ranks (hover the last chip for the others);
- **🔊** plays the word: JapanesePod101 for Japanese, and recordings from Wiktionary and Lingua Libre for every language. Click again for the next recording. These come from the Internet: nothing is sent until you click;
- the **Characters** of the word, with a character dictionary;
- a **+ Card** button.

With the keyboard, while the popup is open:

| Key | Action |
| --- | ------ |
| `↑` `↓` (or `K` `J`) | Pick a result |
| `Enter` or `C` | Make a card from it |
| `A` | Play the word |
| `P` | Play the sentence (books with audio) |
| `1` `2` `3` `4` | Status: new, learning, known, ignored |
| `Esc` | Close |

In the reader's settings (Aa), *Look up words* can be set to *Shift + hover* (like Yomitan), or *Off* if you prefer to keep using Yomitan.

## Word colours

The reader colours the words of the book by status, so you see at a glance what you don't know yet:

| Status   | Colour |
| -------- | ------ |
| New      | blue   |
| Learning | yellow |
| Known, ignored | none |

When two coloured words touch (Chinese, Japanese), every other one is a bit darker, so you can see where each word ends.

The text is split into words with your dictionaries, like the popup does: the longest word found from each character, conjugated forms included (泣いていた is the word 泣く). In Korean, the particles after a noun aren't coloured (친구와 is 친구 + 와). Words missing from your dictionaries (names, typos...) aren't coloured, and neither are rare or dialect words when a split into common words fits. Change a status in the popup, or make a card, and every occurrence of the word changes colour.

In the reader's settings (Aa), *Colour words* can be turned *Off*. The colours don't change the page itself, so Yomitan or other tools work on it as usual.

## 3. Make cards

**+ Card** opens the card creator, filled in with the word, its reading, the definition of the first dictionary, the sentence (the word in bold) and the book's title. Everything can be edited before sending:

- tick other dictionaries to add their definitions;
- add an image: *Choose a file*, drop one on the window, paste one with Ctrl+V, or paste a link;
- add the word's audio or the sentence's audio the same way. The word's audio is filled in when an online recording exists, and for a book [converted with its audio](reader.md#audio-of-a-converted-book), so is the sentence's;
- when the sentence has no audio, it is read by the voice chosen for its language in **Settings › Anki** (*Voice reading sentences without audio*), with the same Edge-TTS voices as for generating a book's audio (an Internet connection is needed). Pick another voice under *Sentence audio* and click **Generate** to try it; choose *None* in the settings to only generate by hand;
- the sentence's translation is filled in, offline, in the language chosen in **Settings › Anki** (*Sentence translation*, English by default, *None* to turn it off). It uses [Argos Translate](https://github.com/argosopentech/argos-translate): the first time a language is translated, its model (about 100 MB) is downloaded. Cantonese and Taiwanese Hokkien have no model;
- edit the translation, add notes and tags.

**Add to Anki** sends the card straight away. **Save for later** keeps it in MiningCat.

The word becomes *learning* as soon as the card is made.

## 4. Connect Anki

Settings › **Anki**

1. In Anki, install the AnkiConnect add-on: *Tools › Add-ons › Get Add-ons…*, code `2055492159`, then restart Anki.
2. Click *Test the connection*.
3. Under **New cards**, for each language you mine, choose the deck and the note type. MiningCat proposes what goes in each field of your note type from the field names (Hanzi → Word, Pinyin → Reading, Meaning → Definition…); change anything that doesn't fit, then *Save*.

!!! tip "Zhuyin"
    CC-CEDICT only gives pinyin. A *Zhuyin* or *Bopomofo* field gets **Zhuyin (Mandarin, from the reading)**: MiningCat converts the pinyin (說話 shuōhuà → ㄕㄨㄛ ㄏㄨㄚˋ). The pronunciation is the dictionary's: for the few words read differently in Taiwan (垃圾...), check the card.

### When Anki is closed

Cards wait in MiningCat (Settings › **Cards**, with a counter) and are sent at the next sync. You can also export them as an `.apkg` file and open it in Anki, AnkiDroid or AnkiMobile. Exported cards use a note type called “MiningCat”.

## 5. Word statuses from Anki

Under **Word statuses from Anki**, add the decks that hold the words you already study, with the name of the field that contains the word (and optionally the reading). At each **Sync now**, MiningCat:

1. sends the cards that were waiting;
2. reads these decks: a word is *learning* while its card is young, and *known* once its interval reaches the number of days you chose (21 by default, Anki's “mature”). Suspended cards are ignored;
3. updates the words of the cards made in MiningCat, wherever they are.

Words you marked *known* or *ignored* yourself are never changed by a sync.

## Languages and Chinese characters

Each language has its own words: knowing 說 in Mandarin says nothing about Cantonese. Settings › **Languages & words** lists them.

For Mandarin and Cantonese, choose the characters you learn: **Traditional**, **Simplified** or **Both**.

- Words whose characters are the same in both scripts count for both.
- If you learn Traditional and look up 说话 in a simplified book, the word is saved as 說話, with Taiwan's characters for Mandarin (里面 is saved as 裡面) and Hong Kong's for Cantonese.
- Words written the same way in both scripts are saved as they are: 了解 and 台灣 are already traditional.
- When you know a word in the other script, the popup tells you (“You know this word in Simplified: 说话”).

## Current limits

- Words are found from the longest dictionary match, without grammar analysis: a Japanese sentence can now and then be split in an unexpected place.
