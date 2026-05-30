# AudiobookMiner

## Description

This project is meant to create _mineable_ videos, out of audiobooks and/or ebooks, so that you can use it for language learning (with tools like Migaku or asbplayer).  
**This is only for mandarin for now! Upcoming languages later on.**  
Supports both Chinese Mandarin and Taiwanese mandarin.
The GUI lets you convert characters if needed.

I will make it more polyvalent in the future and support more languages.
Contributions and issues are very appreciated!

### How to use it
This project is fairly recent and has only been tested with a handful of books.

The simplest way to use :

1. Run `make install`
2. Run `make gui`
3. Follow the instructions.

You can use an ebook in .epub format, and/or audiobook in .mp3 or .m4b.

### Language options 
- Language : select the input's files original language
- Convert to : (available with mandarin) converts simplified <-> traditional characters if needed
### Modes 
There are 3 modes in the GUI :

##### Standard mode
- Provide an ebook and its corresponding audio files.
- You will get .mp4 videos (one per chapter) with the audiobook's audio and subtitles made from the ebook.

##### Generate subtitles mode
- Provide audio files.
- You will get .mp4 videos (one per chapter) with the audiobook's audio and generated subtitles.
This mode gives less accurate subtitles, but it's useful if you don't have the ebook.

##### Generate audio mode
- Provide the ebook file.
- You will get .mp4 videos (one per chapter) generate audio (TTS) with subtitles made from the ebook.
This mode generates audio, which is way less natural than an actual narrator, but it's great if you don't have the audio files.

### Precision
If using standard mode or generate subtitles, you will also have the precision option.  
The subtitles timing are generated using Whisper. this allows you to select which Whisper model you want to use.  
- Base (default) : recommended for most usages
- Tiny : recommended for standard mode, should be a little bit faster
- Small, Medium and Large : only recommended for "generate subtitles" mode, as this takes longer to generate. Should give better subtitles (useless in standard mode because we use the ebook.)

### Chapter selection
You can select specific chapters to target.
this is useful if you ebook doesn't match exactly with the audio, for example if it has an table of content of a preface.
In the UI, just select (highlight) chapters.  
In the CLI, use the "range" option.
