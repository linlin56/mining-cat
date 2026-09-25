# Add a video platform

The video feature downloads a video from an online platform (or takes a local file), transcribes it with Whisper or reads its hardsubs with OCR, and reuses the subtitles the platform already provides when there are some.

Each platform is a small, self-contained **handler** module in `src/video_handlers/`, built on [yt-dlp](https://github.com/yt-dlp/yt-dlp). Use the existing ones as references:

- `instagram.py`: the simplest handler, with a platform-specific option (`app_id`);
- `youtube.py`: also downloads the existing captions;
- `bilibili.py`: a plain download.

Local files don't need a handler: `video.run()` skips the download step when it's given `video_path` instead of `url`.

!!! tip
    Before writing anything, check that yt-dlp supports the platform in its [list of supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

## 1. Write the handler

Create `src/video_handlers/your_site.py`. A handler exposes two things:

- `DOMAINS`: the domains it handles, without `www.`;
- `download(url, output_dir, **_ignored) -> Path`: downloads the video and returns the path of the downloaded file.

```python
from pathlib import Path

import yt_dlp

from video_handlers._common import BASE_YDL_OPTS, resolve_downloaded_path

DOMAINS = ("your-site.com", "m.your-site.com")


def download(url: str, output_dir: Path, **_ignored) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        **BASE_YDL_OPTS,
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return resolve_downloaded_path(ydl, info)
```

`video.run()` calls every handler's `download()` with the same keyword arguments (`app_id`, `language`...), since it doesn't know in advance which handler will be picked. Keep `**_ignored` in the signature and only name the arguments you use.

`BASE_YDL_OPTS` sets retries and quiet output; `resolve_downloaded_path()` returns the downloaded file and logs when the download was skipped because the file already exists.

If yt-dlp needs platform-specific options (headers, cookies...), check the `extractor_args` supported by the extractor in the [yt-dlp README](https://github.com/yt-dlp/yt-dlp#extractor-arguments). See how `instagram.py` passes `app_id`.

## 2. Optional: reuse the platform's subtitles

If the platform provides subtitles (like YouTube captions), have yt-dlp download them next to the video, as `.srt`, in the target language. `youtube.py` does it with:

```python
"writesubtitles": True,
"writeautomaticsub": True,
"subtitleslangs": LANG_CODES.get(language, [language.value.whisper_code]),
"subtitlesformat": "srt",
```

`video.run()` then finds them automatically and adds them as a **Source** track. If subtitles can't be downloaded (rate limit, language not available), fall back to downloading the video alone, as `youtube.py` does: the user still gets the Whisper track.

If the platform has no subtitles, skip this step.

## 3. Register the handler

In `src/video_handlers/__init__.py`, import your module and add it to `_HANDLER_MODULES`:

```python
from . import bilibili, instagram, your_site, youtube

_HANDLER_MODULES = (bilibili, instagram, your_site, youtube)
```

`get_handler()` now dispatches URLs of your domains to your handler. To show the platform in the GUI, add it to `TARGET_WEBSITES` in `src/gui_components/video_panel.py`, with an example URL in the placeholder mapping below it.

## 4. Tests

- `src/tests/video_handlers_your_site.test.py`: mirror `video_handlers_instagram.test.py` / `video_handlers_youtube.test.py`. Mock `yt_dlp.YoutubeDL` and check the `ydl_opts` it receives and the returned path.
- `src/tests/video_handlers.test.py`: add `get_handler()` cases for your domains (with and without `www.`).
- If you added subtitle reuse, add a case to `src/tests/video.test.py` similar to `test_run_includes_platform_subtitle_when_present`.

!!! warning "Never point a test at a real URL"
    Tests must never hit the network. Note that `video_downloader.test.py::test_download_video_unknown_host_raises` uses a TikTok URL as an example of an unsupported platform: **if you add TikTok**, update this test (and any other) to use another unsupported platform.

## 5. Documentation

Add the platform to the [supported platforms table](../how-to-use/video.md#from-the-web) and to the README.

## Checklist

- [ ] Handler module in `src/video_handlers/` with `DOMAINS` and `download(url, output_dir, **_ignored)`
- [ ] Registered in `_HANDLER_MODULES` in `src/video_handlers/__init__.py`
- [ ] Added to `TARGET_WEBSITES` in `src/gui_components/video_panel.py`
- [ ] Subtitle reuse implemented if the platform provides subtitles (optional)
- [ ] Handler tests added (mocked `yt_dlp.YoutubeDL`, no network)
- [ ] `get_handler()` tests added in `src/tests/video_handlers.test.py`
- [ ] Docs and README updated
- [ ] `make test` passes
