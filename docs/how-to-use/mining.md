# Dictionaries & Anki cards

MiningCat has its own dictionary popup and card creator, so you don't need to install Yomitan. Everything is set up in **Settings** (link at the top of the converter and the library, or <http://127.0.0.1:5050/settings/>).

## 1. Import dictionaries

Settings › **Dictionaries** › *Choose a .zip…*

MiningCat reads dictionaries in [Yomitan's format](https://github.com/yomidevs/yomitan), so the dictionaries made for Yomitan work as they are: for example CC-CEDICT (Mandarin), words.hk (Cantonese), JMdict (Japanese), and frequency lists.

- The language is detected from the dictionary's words. If it can't be, choose it in the list before importing.
- Results are shown in the order of the list: use ↑ ↓ to change it. Untick a dictionary to hide it without deleting it.
- When you've imported a frequency list, more frequent words come first in the results.

Dictionaries are stored in `library/miningcat.db`, with your words and cards.

## 2. Look up words in the reader

Click a word in the reader. The popup shows:

- the word, its reading, and how it was conjugated when you clicked an inflected form (Japanese, French, Spanish…: 泣いていた gives 泣く « -て « -いる « -た);
- the definitions of every dictionary;
- the word's **status**: new, learning, known or ignored. Click to change it;
- a **+ Card** button.

In the reader's settings (Aa), *Look up words* can be set to *Shift + hover* (like Yomitan), or *Off* if you prefer to keep using Yomitan.

## 3. Make cards

**+ Card** opens the card creator, filled in with the word, its reading, the definition of the first dictionary, the sentence (the word in bold) and the book's title. Everything can be edited before sending:

- tick other dictionaries to add their definitions;
- add an image: *Choose a file*, drop one on the window, paste one with Ctrl+V, or paste a link;
- add the word's audio or the sentence's audio the same way;
- add a translation, notes and tags.

**Add to Anki** sends the card straight away. **Save for later** keeps it in MiningCat.

The word becomes *learning* as soon as the card is made.

## 4. Connect Anki

Settings › **Anki**

1. In Anki, install the AnkiConnect add-on: *Tools › Add-ons › Get Add-ons…*, code `2055492159`, then restart Anki.
2. Click *Test the connection*.
3. Under **New cards**, for each language you mine, choose the deck and the note type. MiningCat proposes what goes in each field of your note type from the field names (Hanzi → Word, Zhuyin → Reading, Meaning → Definition…); change anything that doesn't fit, then *Save*.

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
- If you learn Traditional and look up 说话 in a simplified book, the word is saved as 說話.
- When you know a word in the other script, the popup tells you (“You know this word in Simplified: 说话”).

## Current limits

- Korean lookups only find dictionary forms: conjugated forms aren't recognized yet.
- Single-character (kanji/hanzi) dictionaries aren't supported yet: only word dictionaries and frequency lists.
- Words aren't coloured by status in the text yet.
