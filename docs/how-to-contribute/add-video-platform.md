# Add a video platform

The video feature downloads a video from an online platform (or takes a local file), transcribes it with Whisper or reads its hardsubs with OCR, and reuses the subtitles the platform already provides when there are some.

Each platform is a **handler**: a `VideoHandler` subclass in `src/miningcat/infrastructure/downloads/`, built on [yt-dlp](https://github.com/yt-dlp/yt-dlp). Use the existing ones as references:

- `instagram.py`: the simplest handler, with a platform-specific option (`app_id`);
- `youtube.py`: also downloads the existing captions;
- `bilibili.py`: a plain download.

Local files don't need a handler: the video pipeline (`application/converter/video_subtitles.py`) skips the download when its request has a `video_path` instead of a `url`.

!!! tip
    Before writing anything, check that yt-dlp supports the platform in its [list of supported sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

## 1. Write the handler

Create `src/miningcat/infrastructure/downloads/your_site.py`. A handler says how it is shown in the converter and which URLs it takes, and downloads:

- `website`: its name in the converter's list of websites;
- `domains`: the domains it handles, without `www.`;
- `url_hint`: an example URL, shown as a placeholder;
- `download(url, output_dir, **_ignored) -> Path`: downloads the video and returns the downloaded file.

```python
from pathlib import Path

import yt_dlp

from miningcat.infrastructure.downloads.handler import VideoHandler, resolve_downloaded_path


class YourSiteHandler(VideoHandler):
    """Videos of Your Site."""

    website = "Your Site"
    domains = ("your-site.com", "m.your-site.com")
    url_hint = "https://www.your-site.com/watch/..."

    def download(self, url: str, output_dir: Path, **_ignored) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        with yt_dlp.YoutubeDL(self._options(output_dir)) as ydl:
            return resolve_downloaded_path(ydl, ydl.extract_info(url, download=True))
```

Every handler's `download()` is called with the same keyword arguments (`app_id`, `language`...), since the caller doesn't know in advance which handler will be picked. Keep `**_ignored` in the signature and only name the arguments you use.

`self._options(output_dir, **extra)` gives yt-dlp's options (retries, quiet output, MP4 output file named after the video's id); `resolve_downloaded_path()` returns the downloaded file and logs when the download was skipped because the file already exists.

If yt-dlp needs platform-specific options (headers, cookies...), check the `extractor_args` supported by the extractor in the [yt-dlp README](https://github.com/yt-dlp/yt-dlp#extractor-arguments). See how `instagram.py` passes `app_id`.

## 2. Optional: reuse the platform's subtitles

If the platform provides subtitles (like YouTube captions), have yt-dlp download them next to the video, as `.srt`, in the target language. `youtube.py` does it with `subtitle_options(language)`, which uses the caption codes of the language's profile (`language.profile.youtube_caption_codes`).

The video pipeline then finds them automatically and adds them as a **Source** track. If subtitles can't be downloaded (rate limit, language not available), fall back to downloading the video alone, as `youtube.py` does: the user still gets the Whisper track.

If the platform has no subtitles, skip this step.

## 3. Register the handler

In `src/miningcat/infrastructure/downloads/registry.py`, add an instance of your handler to the registry, in the order of the converter's list:

```python
video_handlers = VideoHandlerRegistry([InstagramHandler(), YouTubeHandler(), BilibiliHandler(), YourSiteHandler()])
```

That's all: `get_handler()` dispatches URLs of your domains to it, and the converter lists it with its example URL.

## 4. Tests

- `src/tests/infrastructure/downloads/your_site.test.py`: mirror `instagram.test.py` / `youtube.test.py`. Mock `yt_dlp.YoutubeDL` and check the options it receives and the returned path.
- `src/tests/infrastructure/downloads/registry.test.py`: add `get_handler()` cases for your domains (with and without `www.`).
- If you added subtitle reuse, add a case to `src/tests/application/converter/video_subtitles.test.py` similar to `test_run_includes_platform_subtitle_when_present`.

!!! warning "Never point a test at a real URL"
    Tests must never hit the network. Note that `video_download.test.py::test_download_video_unknown_host_raises` uses a TikTok URL as an example of an unsupported platform: **if you add TikTok**, update this test (and any other) to use another unsupported platform.

## 5. Documentation

Add the platform to the [supported platforms table](../how-to-use/video.md#from-the-web) and to the README.

## Checklist

- [ ] `VideoHandler` subclass in `src/miningcat/infrastructure/downloads/`, with `website`, `domains`, `url_hint` and `download()`
- [ ] Registered in `src/miningcat/infrastructure/downloads/registry.py`
- [ ] Subtitle reuse implemented if the platform provides subtitles (optional)
- [ ] Handler tests added (mocked `yt_dlp.YoutubeDL`, no network)
- [ ] `get_handler()` tests added in `src/tests/infrastructure/downloads/registry.test.py`
- [ ] Docs and README updated
- [ ] `make test` passes
