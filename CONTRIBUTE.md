# Contributing

## Add a language

The steps below cover places in the codebase you need to touch to add a new language.
This is subject to change as we are still in early dev.

The priority is to add languages :

- Supported by Migaku
- Supported by edge-tts and Whisper

I may be able to add new languages that I don't speak, but help is wanted to double-check!

---

### 1. `src/language.py` - define the language

Add a new member to the `Language` enum:

```python
YOUR_LANGUAGE = LangConfig(
    # displayed in the GUI dropdown. Region is for languages having different standards, like mandarin with Taiwan variants.
    label='Your Language - Region',
    # Whisper / stable-whisper language code (BCP-47, e.g. 'ko', 'fr') Check whisper docs.
    whisper_code='xx',
    # ISO 639-2 three-letter code used in MP4 subtitle metadata (language of subtitles)
    iso639_2='xxx',
    # sentence-closing punctuation chars for your language
    closing_punct=frozenset('…'),
    # sentence-opening punctuation chars (e.g. opening quotes, brackets)
    opening_punct=frozenset(''),
    # regex to strip in-text vocabulary annotations (use r'' if none)
    vocab_annotation_pattern=r'...',
)
```

**Fields to research:**

- `whisper_code` - see the Whisper supported languages list
- `iso639_2` - look up your language
- `closing_punct` - sentence-final punctuation that Whisper sometimes wrongly places at the start of the next segment; used by `align.fix_leading_punct()`
- `opening_punct` - sentence-opening punctuation (quotes, brackets) used by `align.fix_trailing_opening_punct()` and `align.restore_opening_punct()` to avoid orphaned opening marks at segment boundaries; use `frozenset('')` if your language has none
- `vocab_annotation_pattern` - regex matching glossary or ruby annotations embedded in ebook text that should be stripped before alignment (e.g. `\[\d+\]` for Chinese, `［＃.+?］` for Japanese Aozora Bunko format); use `r''` if your books don't use any

No other changes are needed in `src/language.py` - `all_labels()`, `ids()`, and `from_id()` are derived automatically from the enum members.

---

### 2. `src/gui_components/constants.py` - add TTS voices

Add your language's edge-tts voices to the two dictionaries:

**`_VOICES_FOR_LANGUAGE`**

```python
Language.YOUR_LANGUAGE: [
    ("VoiceName - Language (Region), female", "xx-REGION-VoiceNameNeural"),
    ("VoiceName - Language (Region), male",   "xx-REGION-VoiceNameNeural"),
],
```

**`DEFAULT_VOICE_FOR_LANGUAGE`**:

```python
Language.YOUR_LANGUAGE: "VoiceName - Language (Region), female",
```

---

### 3. `src/chinese_converter.py` - Chinese-only, skip if not applicable

This file handles script conversion between Simplified and Traditional Chinese using OpenCC.
Mandarin is already supported.
May be useful for Cantonese (HK traditional is supported by OpenCC)

- Add an entry in `SCRIPT_FOR_LANGUAGE` mapping your `Language` member to its OpenCC script code
- Add the relevant conversion paths in `_CONFIGS` and punctuation maps in `_PUNCT_MAP`

---

### 4. `src/main.py` - expose the language in the CLI

The `--language` argument in the `align`, `transcribe`, and `export` subcommands is populated from `Language.ids()`, so **no change is needed** - your new enum member is picked up automatically.

---

### 5. Tests - add mock files and test cases

**Mock files** (`src/tests/mock/`):

Create an epub with few lines in the language. You can do that we a text editor.
Add these language in a txt file as well, and in the `src/tests/mock/README.md`.

| File           | Purpose                                       |
| -------------- | --------------------------------------------- |
| `book_xx.epub` | Short EPUB in your language (a few sentences) |
| `book_xx.txt`  | Same content as plain text                    |
| `srt_xx.srt`   | Matching SRT with correct timecodes           |

Replace `xx` with the BCP-47 code you use for your language (e.g. `ko`, `fr-FR`). Keep the files short - see `src/tests/mock/README.md` for the expected format and content conventions.

**`src/tests/shared.py`** - declare the mock path constants and skip decorators:

```python
MOCK_EPUB_XX = MOCK_DIR / "book_xx.epub"
MOCK_TXT_XX  = MOCK_DIR / "book_xx.txt"
MOCK_SRT_XX  = MOCK_DIR / "srt_xx.srt"

skip_if_no_epub_xx = pytest.mark.skipif(not MOCK_EPUB_XX.exists(), reason="tests/mock/book_xx.epub not available")
skip_if_no_txt_xx  = pytest.mark.skipif(not MOCK_TXT_XX.exists(),  reason="tests/mock/book_xx.txt not available")
skip_if_no_srt_xx  = pytest.mark.skipif(not MOCK_SRT_XX.exists(),  reason="tests/mock/srt_xx.srt not available")
```

**`src/tests/language.test.py`** - test the new enum member:

- Add parametrize cases for `vocab_annotation_pattern` (true positives and false positives)
- Add an assertion for the `iso639_2` value in `test_iso639_2_values()`
- Add `Language.from_id("your_language")` cases in `test_from_id_case_insensitive()`

**`src/tests/epub.test.py`** - add the EPUB and TXT parametrize params (follow the pattern used for `zh-TW`, `zh-CN`, `ja`) with a matching `EXPECTED_LINES_XX` list, and add SRT content/timecode tests.

---

### Checklist

- [ ] New `Language` enum member in `src/language.py`
- [ ] `closing_punct` and `opening_punct` verified against real text samples
- [ ] `vocab_annotation_pattern` tested (or confirmed unused)
- [ ] edge-tts voices added in `src/gui_components/constants.py` (or documented as unavailable)
- [ ] `src/chinese_converter.py` updated if adding a Chinese variant
- [ ] Mock files created in `src/tests/mock/`
- [ ] Constants and skip markers added in `src/tests/shared.py`
- [ ] Test cases added in `src/tests/language.test.py`
- [ ] Test cases added in `src/tests/epub.test.py`
- [ ] `make test` passes

---

## Add a video platform

The "Video from Web" feature (`src/video.py`) downloads a video from an online platform, transcribes it with Whisper, and optionally reuses subtitles the platform already provides. Each platform is a self-contained handler module in `src/video_handlers/`; `src/video_handlers/instagram.py` and `src/video_handlers/youtube.py` are the reference implementations.

---

### 1. `src/video_handlers/your_site.py` - the handler module

`video.run()` calls every handler's `download()` with the same set of keyword arguments (`app_id`, `language`, ...) regardless of platform, since it doesn't know ahead of time which handler will be picked.

If yt-dlp needs platform-specific options (custom headers, extractor args, cookies...), check the [yt-dlp README](https://github.com/yt-dlp/yt-dlp) for the extractor's supported `extractor_args` first - see `instagram.py`'s `app_id` handling for an example.

---

### 2. Optional: reuse subtitles the platform already provides

If the platform can serve existing subtitles (like YouTube captions), have yt-dlp download them alongside the video!

If the platform has no subtitle concept, skip this step entirely - the plain `download()` from step 1 is enough, and the final video will just get the single Whisper track (like Instagram).

---

### 3. `src/video_handlers/__init__.py` - register the handler

## Add the new handler here.

### 4. Tests

- `src/tests/video_handlers_your_site.test.py` - mirror `video_handlers_instagram.test.py` / `video_handlers_youtube.test.py`: mock `yt_dlp.YoutubeDL` and check the built `ydl_opts` and returned path, no real network calls.
- `src/tests/video_handlers.test.py` - add `get_handler()` cases for your new domain(s).
- If you added subtitle reuse (step 2), add a case to `src/tests/video.test.py` similar to `test_run_includes_platform_subtitle_when_present`.

**Never point a test at a real URL** - `video_downloader.test.py::test_download_video_unknown_host_raises`.
So far I used Tiktok as it is not supported. **If you want to add TikTok** please also update the older tests to point to a non-supported platform!

---

### Checklist

- [ ] New handler module in `src/video_handlers/` with `DOMAINS` and `download(url, output_dir, **_ignored)`
- [ ] Registered in `_HANDLER_MODULES` in `src/video_handlers/__init__.py`
- [ ] Subtitle reuse implemented if the platform supports it (optional)
- [ ] Handler tests added (mocked `yt_dlp.YoutubeDL`, no real network calls)
- [ ] `get_handler()` dispatch tests added in `src/tests/video_handlers.test.py`
- [ ] README's "Video from Web" > "Supported platforms" list updated
- [ ] `make test` passes
