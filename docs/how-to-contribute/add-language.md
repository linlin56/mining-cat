# Add a language

This page lists every place in the codebase to touch when adding a language. It's subject to change as the project is still in early development.

Priority goes to languages that are supported by [Whisper](https://github.com/openai/whisper#available-models-and-languages) and [edge-tts](https://github.com/rany2/edge-tts).

Other TTS and means of transcriptions may be added in the future.

You can add a language you don't speak, but please ask a native speaker to double-check the results, and say so in your pull request.

## 1. Define the language

**`src/language.py`**: add a member to the `Language` enum.

```python
YOUR_LANGUAGE = LangConfig(
    # Displayed in the GUI dropdown. Add a region for languages with several standards
    # (e.g. 'Mandarin - Taiwan (Traditional)').
    label='Your Language - Region',
    # Whisper language code (e.g. 'ko', 'fr').
    whisper_code='xx',
    # ISO 639-2 three-letter code, used in the MP4 subtitle track metadata.
    iso639_2='xxx',
    # Sentence-closing punctuation.
    closing_punct=frozenset('.?!…'),
    # Sentence-opening punctuation (opening quotes, brackets...).
    opening_punct=frozenset('“'),
    # Regex matching vocabulary annotations to strip from the ebook text, r'' if none.
    vocab_annotation_pattern=r'',
    # Language code for Apple Vision OCR (BCP-47, e.g. 'ko-KR').
    ocr_lang_apple='xx-XX',
    # Language code for EasyOCR (e.g. 'ko', 'ch_tra').
    ocr_lang_easyocr='xx',
)
```

What each field is used for:

| Field                      | Used for                                                                                                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `whisper_code`             | Transcription and alignment. See Whisper's list of supported languages.                                                                                                  |
| `iso639_2`                 | Subtitle language metadata in the MP4 files.                                                                                                                             |
| `closing_punct`            | Whisper sometimes puts sentence-final punctuation at the start of the next segment: `align.fix_leading_punct()` moves it back.                                             |
| `opening_punct`            | Avoids orphaned opening marks at segment boundaries (`align.fix_trailing_opening_punct()`, `align.restore_opening_punct()`). Use `frozenset('')` if your language has none. |
| `vocab_annotation_pattern` | Glossary or ruby annotations embedded in ebooks, stripped before alignment (e.g. `\[\d+\]` for Chinese, `［＃.+?］` for Japanese Aozora Bunko). Use `r''` if unused.          |
| `ocr_lang_apple`           | OCR on macOS ([Apple Vision supported languages](https://developer.apple.com/documentation/vision/vnrecognizetextrequest)).                                                |
| `ocr_lang_easyocr`         | OCR on other platforms ([EasyOCR supported languages](https://www.jaided.ai/easyocr/)).                                                                                   |

Verify the punctuation sets against real text samples: quotes differ a lot between languages (`« »`, `„ "`, `「 」`...).

Nothing else is needed in `language.py`: `all_labels()`, `ids()` and `from_id()` are derived from the enum. The CLI `--language` choices and the GUI dropdown pick up the new member automatically.

## 2. Add TTS voices

**`src/gui_components/constants.py`**: add the language's edge-tts voices to `_VOICES_FOR_LANGUAGE`:

```python
Language.YOUR_LANGUAGE: [
    ("VoiceName - Language (Region), female", "xx-REGION-VoiceNameNeural"),
    ("VoiceName - Language (Region), male",   "xx-REGION-VoiceNameNeural"),
],
```

and pick the default one in `DEFAULT_VOICE_FOR_LANGUAGE`:

```python
Language.YOUR_LANGUAGE: "VoiceName - Language (Region), female",
```

List the available voices with `edge-tts --list-voices | grep xx-`.

If Whisper only supports the language with its large models (like Cantonese), add its `whisper_code` to `LARGE_ONLY_WHISPER_CODES` in the same file, so that the GUI only offers **Large** and **Turbo**.

## 3. Language-specific tables

Depending on the language, update the following tables (all keyed by `Language`):

| File                                        | Table                   | When                                                                                                    |
| ------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------- |
| `src/video_handlers/youtube.py`             | `LANG_CODES`            | Always: YouTube caption codes to try, in order of preference.                                            |
| `src/ocr_mining/dedup.py`                   | `_PATTERN_FOR_LANGUAGE` | **Required for non-Latin scripts**, otherwise all OCR text is rejected as implausible.                   |
| `src/frequency/word_frequency.py`           | `_SEGMENTERS`           | Languages written without spaces between words need a tokenizer (like jieba for Chinese).               |
| `src/frequency/character_frequency.py`      | `_CHAR_PATTERN`, `_LANG_CODE` | Only for CJK languages, to enable the Kanji Grid character list.                                         |
| `src/chinese_converter.py`                  | `SCRIPT_FOR_LANGUAGE`, `_CONFIGS`, `_PUNCT_MAP` | Only for Chinese variants: OpenCC script and conversion paths.                   |

## 4. Tests

### Mock files

In `src/tests/mock/`, create three short files with the same few sentences (follow the content of the existing mocks: a greeting, a short sentence, a longer one, a quoted sentence with punctuation):

| File           | Content                                    |
| -------------- | ------------------------------------------ |
| `book_xx.epub` | A short EPUB in your language             |
| `book_xx.txt`  | The same content as plain text            |
| `srt_xx.srt`   | A matching SRT with correct timecodes     |

Replace `xx` with the BCP-47 code of your language (e.g. `ko`, `en-GB`). An EPUB can be created with any EPUB editor (e.g. [Sigil](https://sigil-ebook.com/)) or exported from a text editor. Document the files and their content in `src/tests/mock/README.md`.

### Test code

**`src/tests/shared.py`**: declare the mock paths and skip markers.

```python
MOCK_EPUB_XX = MOCK_DIR / "book_xx.epub"
MOCK_TXT_XX  = MOCK_DIR / "book_xx.txt"
MOCK_SRT_XX  = MOCK_DIR / "srt_xx.srt"

skip_if_no_epub_xx = pytest.mark.skipif(not MOCK_EPUB_XX.exists(), reason="tests/mock/book_xx.epub not available")
skip_if_no_txt_xx  = pytest.mark.skipif(not MOCK_TXT_XX.exists(),  reason="tests/mock/book_xx.txt not available")
skip_if_no_srt_xx  = pytest.mark.skipif(not MOCK_SRT_XX.exists(),  reason="tests/mock/srt_xx.srt not available")
```

**`src/tests/language.test.py`**:

- add `vocab_annotation_pattern` cases (true positives and false positives);
- add the `iso639_2` value in `test_iso639_2_values()`;
- add `Language.from_id("your_language")` cases in `test_from_id_case_insensitive()`.

**`src/tests/epub.test.py`**: add the EPUB and TXT parametrize entries (follow the `zh-TW`, `zh-CN`, `ja` pattern) with a matching `EXPECTED_LINES_XX` list, and add the SRT content and timecode tests.

If you updated the tables of step 3, add the matching cases in the related test files (`ocr_mining_dedup.test.py`, `frequency.test.py`...).

## 5. Documentation

Add the language to the list on the [home page](../index.md), to the [language ids](../how-to-use/cli.md#language-ids) of the CLI reference, and to the README.

## Checklist

- [ ] New `Language` member in `src/language.py`
- [ ] `closing_punct` and `opening_punct` checked against real text samples
- [ ] `vocab_annotation_pattern` tested (or confirmed unused)
- [ ] OCR codes set (`ocr_lang_apple`, `ocr_lang_easyocr`)
- [ ] edge-tts voices added in `src/gui_components/constants.py` (or documented as unavailable)
- [ ] YouTube caption codes added in `src/video_handlers/youtube.py`
- [ ] OCR script pattern added in `src/ocr_mining/dedup.py` (non-Latin scripts)
- [ ] Frequency and Chinese conversion tables updated if relevant
- [ ] Mock files created and documented in `src/tests/mock/`
- [ ] Constants and skip markers added in `src/tests/shared.py`
- [ ] Test cases added in `src/tests/language.test.py` and `src/tests/epub.test.py`
- [ ] Docs and README updated
- [ ] `make test` passes
