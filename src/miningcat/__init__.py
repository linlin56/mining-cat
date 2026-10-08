"""MiningCat: turn books, videos and games into language-learning material.

The package follows a layered ("clean") architecture. Dependencies only point inwards:

- `domain`: language data and pure algorithms (text, subtitles, deinflection, OCR clean-up...). Imports nothing
  from the other layers, and does no I/O.
- `application`: the use cases (converter pipelines, dictionary lookups, cards, libraries...). Uses the domain,
  and the infrastructure through its adapters.
- `infrastructure`: adapters to the outside world: SQLite, ffmpeg, Whisper, yt-dlp, AnkiConnect, OCR engines,
  window capture... Uses the domain, never the application.
- `interfaces`: what the user runs: the CLI, the web GUI, the video game page and the legacy Tkinter GUI.
- `config`: where files live and how the app is run, readable from every layer but the domain.
"""
