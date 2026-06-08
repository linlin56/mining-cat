# Contributing

## Add a language

The steps below cover places in the codebase you need to touch to add a new language.
This is subject to change as we are still in early dev.

The priority is to add languages :

- Supported by Migaku
- Supported by edge-tts and Whisper

The owner (me) of the repo is willing to add French, English, Spanish, Italian, Korean.  
I may be able to add new languages that I don't speak, but help is wanted to double-check!

---

### 1. `language.py` — define the language

Add a new member to the `Language` enum:

```python
YOUR_LANGUAGE = LangConfig(
    # displayed in the GUI dropdown. Region is for languages having different standards, like mandarin with Taiwan variants.
    label='Your Language — Region',
    # Whisper / stable-whisper language code (BCP-47, e.g. 'ko', 'fr') Check whisper docs.
    whisper_code='xx',
    # ISO 639-2 three-letter code used in MP4 subtitle metadata (language of subtitles)
    iso639_2='xxx',
    # sentence-closing punctuation chars for your language
    closing_punct=frozenset('…'),
    # regex to strip in-text vocabulary annotations (use r'' if none)
    vocab_annotation_pattern=r'...',
)
```

**Fields to research:**

- `whisper_code` — see the Whisper supported languages list
- `iso639_2` — look up your language
- `closing_punct` — sentence-final punctuation that Whisper sometimes wrongly places at the start of the next segment; used by `align.fix_leading_punct()`. This is to be sure that a sentence doesn't start with a closing parenthesis for example.
- `vocab_annotation_pattern` — regex matching glossary or ruby annotations embedded in ebook text that should be stripped before alignment (e.g. `\[\d+\]` for Chinese, `［＃.+?］` for Japanese Aozora Bunko format); use `r''` if your books don't use any

No other changes are needed in `language.py` — `all_labels()`, `ids()`, and `from_id()` are derived automatically from the enum members.

---

### 2. `gui.py` — add TTS voices

Add your language's edge-tts voices to the two dictionaries:

**`_VOICES_FOR_LANGUAGE`**

```python
Language.YOUR_LANGUAGE: [
    ("VoiceName — Language (Region), female", "xx-REGION-VoiceNameNeural"),
    ("VoiceName — Language (Region), male",   "xx-REGION-VoiceNameNeural"),
],
```

**`_DEFAULT_VOICE_FOR_LANGUAGE`** (line 94):

```python
Language.YOUR_LANGUAGE: "VoiceName — Language (Region), female",
```

---

### 3. `chinese_converter.py` — Chinese-only, skip if not applicable

This file handles script conversion between Simplified and Traditional Chinese using OpenCC.
Mandarin is already supported.
May be useful for Cantonese (HK traditional is supported by OpenCC)

- Add an entry in `SCRIPT_FOR_LANGUAGE` mapping your `Language` member to its OpenCC script code
- Add the relevant conversion paths in `_CONFIGS` and punctuation maps in `_PUNCT_MAP`

---

### 4. `main.py` — expose the language in the CLI

The `--language` argument in the `align`, `transcribe`, and `export` subcommands is populated from `Language.ids()`, so **no change is needed** — your new enum member is picked up automatically.

---

### 5. Tests — add mock files and test cases

**Mock files** (`tests/mock/`):

Create an epub with few lines in the language. You can do that we a text editor.
Add these language in a txt file as well, and in the `tests/mock/README.md`.

| File           | Purpose                                       |
| -------------- | --------------------------------------------- |
| `book_xx.epub` | Short EPUB in your language (a few sentences) |
| `book_xx.txt`  | Same content as plain text                    |
| `srt_xx.srt`   | Matching SRT with correct timecodes           |

Replace `xx` with the BCP-47 code you use for your language (e.g. `ko`, `fr-FR`). Keep the files short — see `tests/mock/README.md` for the expected format and content conventions.

**`tests/shared.py`** — declare the mock path constants and skip decorators:

```python
MOCK_EPUB_XX = MOCK_DIR / "book_xx.epub"
MOCK_TXT_XX  = MOCK_DIR / "book_xx.txt"
MOCK_SRT_XX  = MOCK_DIR / "srt_xx.srt"

skip_if_no_epub_xx = pytest.mark.skipif(not MOCK_EPUB_XX.exists(), reason="tests/mock/book_xx.epub not available")
skip_if_no_txt_xx  = pytest.mark.skipif(not MOCK_TXT_XX.exists(),  reason="tests/mock/book_xx.txt not available")
skip_if_no_srt_xx  = pytest.mark.skipif(not MOCK_SRT_XX.exists(),  reason="tests/mock/srt_xx.srt not available")
```

**`tests/language.test.py`** — test the new enum member:

- Add parametrize cases for `vocab_annotation_pattern` (true positives and false positives)
- Add an assertion for the `iso639_2` value in `test_iso639_2_values()`
- Add `Language.from_id("your_language")` cases in `test_from_id_case_insensitive()`

**`tests/epub.test.py`** — add the EPUB and TXT parametrize params (follow the pattern used for `zh-TW`, `zh-CN`, `ja`) with a matching `EXPECTED_LINES_XX` list, and add SRT content/timecode tests.

---

### Checklist

- [ ] New `Language` enum member in `language.py`
- [ ] `closing_punct` verified against real text samples
- [ ] `vocab_annotation_pattern` tested (or confirmed unused)
- [ ] edge-tts voices added in `gui.py` (or documented as unavailable)
- [ ] `chinese_converter.py` updated if adding a Chinese variant
- [ ] Mock files created in `tests/mock/`
- [ ] Constants and skip markers added in `tests/shared.py`
- [ ] Test cases added in `tests/language.test.py`
- [ ] Test cases added in `tests/epub.test.py`
- [ ] `make test` passes
