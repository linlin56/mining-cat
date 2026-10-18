# E-reader (KOReader)

Read on your e-reader, send the words you look up to MiningCat, and make their cards later on your computer, with
everything the card creator offers: your dictionaries, the voice, an image...

This works with [KOReader](https://koreader.rocks/), on a Kobo, a Kindle, a PocketBook... and with its MiningCat
plugin. The e-reader and the computer must be on the same Wi-Fi, and MiningCat must be running on the computer to
receive the words: until then, they wait on the e-reader.

## In MiningCat

Open **Settings › E-reader** and turn on **Let the e-reader send words**.

MiningCat then also answers on another port (5051 by default) to the devices of your network, but only to receive
words, and only with the token shown below the address. The rest of MiningCat still only answers to this computer.
The first time, macOS may ask whether Python can accept incoming connections: allow it.

Keep this page open: the plugin needs its **address** (`http://192.168.x.x:5051`) and its **token**. **New token**
makes another one, if you think someone else has it: the e-reader then needs the new one.

## Installing the plugin

The plugin is the `koreader/miningcat.koplugin` folder of MiningCat. Copy that folder, with its name, to KOReader's
`plugins` folder:

- **Kobo**: plug the e-reader in, then copy it to `.adds/koreader/plugins/` on the e-reader (`.adds` is a hidden
  folder: on macOS, press `⌘` + `Shift` + `.` in the Finder to see it).
- **Kindle**: `koreader/plugins/`.
- **KOReader on a computer**: the `plugins` folder of its settings folder (macOS: `~/Library/Application Support/koreader/plugins/`).

Restart KOReader.

## Setting it up in KOReader

Open a book, then the menu **Search** (the magnifying glass) › **Settings** › **MiningCat**:

1. **Address**: the address shown in MiningCat (Settings › E-reader).
2. **Token**: the token shown there.
3. **Test the connection**: it tells the language you study in MiningCat.

The e-reader then looks words up in MiningCat's dictionaries: you don't need to install dictionaries in KOReader.

## Looking words up

Look a word up in the book (long press): the popup shows the definitions of your MiningCat
[dictionaries](mining.md), one dictionary per page (◁◁ ▷▷ for the others), the longest word first as in MiningCat's
own popup. On top of each definition:

- the word's reading, its **status** in MiningCat (New, Learning, Known, Ignored) and its frequency rank: no need to
  send a word you know already;
- **Sent already**, when the word waits in MiningCat's E-reader inbox.

KOReader's own dictionaries, if you have some, come after MiningCat's. Without Wi-Fi, or with MiningCat closed, the
popup shows only KOReader's dictionaries (or why MiningCat's can't be reached). To use only KOReader's, untick
**Search › Settings › MiningCat › Look words up in MiningCat's dictionaries**.

## Sending words

The dictionary popup has a **Send to MiningCat** button: the word goes to MiningCat with its sentence, the book and
the page.

!!! tip
    If you don't see the button, it may be hidden by your popup's button layout: add it from the dictionary
    settings (Search › Settings › Dictionary settings › Customize buttons).

When the Wi-Fi is off or MiningCat isn't running, the word is kept on the e-reader. The words waiting are sent as soon
as the Wi-Fi comes back on, or from **Search › Settings › MiningCat › Send the words waiting**.

The plugin never turns the Wi-Fi on by itself: you can read and send words offline all along, and send them all at
the end of the session.

## Making the cards

Open **E-reader** from MiningCat's home page (its tile shows how many words are waiting). Each word is there with its
sentence, the word you looked up underlined:

1. Click a word to look it up in your [dictionaries](mining.md), like in the [Clipboard](clipboard.md): the word you
   looked up on the e-reader, or any other of the sentence.
2. Make its card in the card creator: the sentence is the one sent by the e-reader, the source is the book and its page.
3. Once the card is made, the sentence leaves the list. **Dismiss** removes it without a card.

The words are listed by language: those of a book in another language wait on that language's page. A book that
doesn't tell its language goes to the language you study.
