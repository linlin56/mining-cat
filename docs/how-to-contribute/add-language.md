# Add a language

This page lists every place in the codebase to touch when adding a language. It's subject to change as the project is still in early development.

Priority goes to languages that are supported by [Whisper](https://github.com/openai/whisper#available-models-and-languages) and [edge-tts](https://github.com/rany2/edge-tts).

Other TTS and means of transcriptions may be added in the future.

You can add a language you don't speak, but please ask a native speaker to double-check the results, and say so in your pull request.

## 1. Define the language

Everything MiningCat knows about a language variant is in its **profile**, a member of the `Language` enum in `src/miningcat/domain/languages/language.py`, built with a `LanguageProfileBuilder`. Only state what differs from the defaults:

```python
YOUR_LANGUAGE = (
    # Displayed in the dropdowns. Add a region for languages with several standards
    # (e.g. 'Mandarin - Taiwan (Traditional)').
    LanguageProfileBuilder("Your Language - Region")
    # The study language it belongs to (see study_language.py), its Whisper code, and its ISO 639-2 code.
    .codes(key="xx", whisper="xx", iso639_2="xxx")
    # Sentence-closing and sentence-opening punctuation (opening quotes, brackets...).
    .punctuation(closing=".?!…", opening="“")
    # Language codes of Apple Vision OCR (BCP-47) and EasyOCR. Non-Latin scripts also give their script.
    .ocr(apple="xx-XX", easyocr="xx", script=scripts.LATIN_LETTER)
    # edge-tts voices, (label, voice id), the default one first.
    .voices(
        ("VoiceName - Language (Region), female", "xx-REGION-VoiceNameNeural"),
        ("VoiceName - Language (Region), male", "xx-REGION-VoiceNameNeural"),
    )
    .build()
)
```

What each step of the builder is for:

| Step                        | Default                       | Used for                                                                                                                                                    |
| --------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `codes(key, whisper, iso639_2, tag)` | required             | `key`: the study language (dictionaries, words). `whisper`: transcription and alignment. `iso639_2`: subtitle metadata in the MP4 files. `tag`: the BCP-47 tag of its texts, when it isn't the Apple OCR code (Cantonese is `yue-Hant`). |
| `punctuation(closing, opening)` | none                      | Whisper sometimes puts sentence-final punctuation at the start of the next segment, and drops opening marks (`domain/subtitles/punctuation.py`).               |
| `vocab_annotations(pattern)` | none                         | Glossary or ruby annotations embedded in ebooks, stripped before alignment (e.g. `\[\d+\]` for Chinese, `［＃.+?］` for Japanese Aozora Bunko).               |
| `ocr(apple, easyocr, script)` | required (script: Latin)   | OCR on macOS ([Apple Vision languages](https://developer.apple.com/documentation/vision/vnrecognizetextrequest)) and elsewhere ([EasyOCR languages](https://www.jaided.ai/easyocr/)). **Non-Latin scripts must give their `script`** (`scripts.CJK`, `scripts.HANGUL`...): OCR text without a character of the script is rejected as noise. |
| `voices(...)`               | none                          | The "Generate audio" mode and the sentence audio of cards. List them with `edge-tts --list-voices \| grep xx-`.                                             |
| `youtube_captions(*codes)`  | the Whisper code              | YouTube caption codes to try, in order of preference.                                                                                                       |
| `word_segmentation(...)`    | `SPACES`                      | Languages written without spaces need a tokenizer for word frequency lists (`CHINESE`: jieba, `JAPANESE`: janome).                                           |
| `character_list(tag, pattern)` | none                       | CJK languages only: enables the Kanji Grid character list.                                                                                                  |
| `chinese_script(script)`    | none                          | Chinese variants only: their OpenCC script (`s`, `tw`, `hk`), for the simplified / traditional conversions (`domain/text/chinese_conversion.py`).            |
| `large_whisper_models_only()` | no                          | Languages Whisper only knows with its large-v3 and turbo models (like Cantonese): the GUI only offers **Large** and **Turbo**.                               |

Verify the punctuation sets against real text samples: quotes differ a lot between languages (`« »`, `„ "`, `「 」`...).

Nothing else is needed: the CLI `--language` choices, the dropdowns, the voices, the YouTube captions and the OCR all read the profile.

## 2. A new study language

If the variant belongs to a language MiningCat doesn't know yet (dictionaries, saved words, cards), add it to `STUDY_LANGUAGES` in `src/miningcat/domain/languages/study_language.py`, with its English and native names. A language written without spaces between words (`without_spaces=True`) is looked up character by character.

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

**`src/tests/domain/languages.test.py`**:

- add `vocab_annotation_pattern` cases (true positives and false positives);
- add the `iso639_2` value in `test_iso639_2_values()`;
- add `Language.from_id("your_language")` cases in `test_from_id_case_insensitive()`.

**`src/tests/application/converter/ebook_extraction.test.py`**: add the EPUB and TXT parametrize entries (follow the `zh-TW`, `zh-CN`, `ja` pattern) with a matching `EXPECTED_LINES_XX` list, and add the SRT content and timecode tests.

If the profile uses a script, a segmentation or a character list, add the matching cases in the related test files (`domain/ocr/similarity.test.py`, `domain/frequency_lists.test.py`...).

## 5. Documentation

Add the language to the list on the [home page](../index.md), to the [language ids](../how-to-use/cli.md#language-ids) of the CLI reference, and to the README.

## Checklist

- [ ] New `Language` member in `src/miningcat/domain/languages/language.py`
- [ ] New study language in `src/miningcat/domain/languages/study_language.py` (if needed)
- [ ] Punctuation checked against real text samples
- [ ] Vocabulary annotations tested (or confirmed unused)
- [ ] OCR codes set, and the script for non-Latin languages
- [ ] edge-tts voices added (or documented as unavailable)
- [ ] YouTube caption codes, word segmentation, character list and Chinese script set if relevant
- [ ] Mock files created and documented in `src/tests/mock/`
- [ ] Constants and skip markers added in `src/tests/shared.py`
- [ ] Test cases added in `src/tests/domain/languages.test.py` and `src/tests/application/converter/ebook_extraction.test.py`
- [ ] Docs and README updated
- [ ] `make test` passes
