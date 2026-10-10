# How to contribute

Contributions are very welcome, whether it's a bug report, a new language, a new video platform or a fix in these docs!

## Ways to help

- **Report a bug or suggest a feature**: open an [issue](https://github.com/linlin56/mining-cat/issues). For bugs, include the language, the mode, your OS and the log shown in the GUI (or the terminal output).
- **Proofread a language**: some languages were added by people who don't speak them. If you do, check the punctuation handling and the subtitles, and report what's wrong.
- **Add a language**: see [Add a language](add-language.md).
- **Add a video platform**: see [Add a video platform](add-video-platform.md).
- **Support video game capture on another OS**: see [Add a capture backend](add-capture-backend.md).
- **Improve the docs**: see [Documentation](#documentation) below.

## Development setup

Follow the [installation steps](../how-to-use/index.md#installation), then check that everything works:

```bash
make test
```

The [Project structure](project-structure.md) page gives an overview of the code.

## Tests

Tests use [pytest](https://docs.pytest.org/) and live in `src/tests/`, in folders that mirror the layers of the package: `tests/domain/`, `tests/application/`, `tests/infrastructure/` and `tests/interfaces/`. Test files are named after what they test, as `<module>.test.py` (e.g. `tests/application/converter/ebook_extraction.test.py` tests `application/converter/steps/ebook_extraction.py`).

```bash
make test                              # run the tests
make coverage                          # run the tests with a coverage report
.venv/bin/python -m pytest src/tests/application/converter/ebook_extraction.test.py -k chapters   # run a subset
```

A few rules:

- **No network in tests.** Mock `yt_dlp.YoutubeDL`, edge-tts, etc. Never point a test at a real URL.
- **Keep mock files small and open.** Test books, texts and subtitles live in `src/tests/mock/`: a few sentences each, written by us, never copyrighted content. Document any new mock in `src/tests/mock/README.md`.
- Shared mock paths and `skipif` markers are declared in `src/tests/shared.py`, with test helpers (`redirect_path()`, `FakeOpenCc`).
- **Never touch the user's files.** `conftest.py` points every folder of `paths` (sources/, output/, library/ and its database) to a temporary folder in every test: use `paths.srt`, `paths.ebook`... rather than building paths yourself.
- **The layers are checked**: `architecture.test.py` fails when a module imports a layer above its own (see [Project structure](project-structure.md)).

### Coverage

The CI fails if coverage drops below **80%**. The rules are in `.coveragerc`.
PR with a failed CI will not be merged.

## Continuous integration

On every push and pull request, GitHub Actions (`.github/workflows/actions.yml`):

1. installs the project on Ubuntu with Python 3.14 (`make install`);
2. runs `make coverage`.

On `main`, it then builds these docs and deploys them to GitHub Pages.

## Pull requests

1. Fork the repository and create a branch from `main`, e.g. `feat/korean-support` or `fix/epub-toc`.
2. Make your changes, with tests.
3. Run `make test` locally.
4. Update the docs if the change is visible to users (new option, new language, new platform...).
5. Open a pull request against `main` and describe what you changed and how you tested it.

Commit messages follow a light [Conventional Commits](https://www.conventionalcommits.org/) style: `feat: bilibili support`, `fix: OCR for Korean`, `docs: ...`.

### GUI changes

You can improve the GUI, but try to keep a nice user experience and change as little as possible. A new option should have a sensible default so that the simple use case stays simple.

## Documentation

These docs are built with [Zensical](https://zensical.org/). The pages are Markdown files in `docs/`, and the navigation is defined in `zensical.toml`.

Preview your changes locally:

```bash
pip install zensical
zensical serve
```

Then open <http://localhost:8000>. When adding a page, add it to the `nav` in `zensical.toml`.

### Screenshots

The screenshots in `docs/assets/screenshots/` are taken by `tools/screenshots.py`. It runs the GUI from a temporary copy of `src/`, with demo data (a short story, small Mandarin and Taigi dictionaries, a generated video, a fake AnkiConnect), so your own library never shows up. Then it drives Chrome with [Playwright](https://playwright.dev/python/) (ffmpeg makes the video):

```bash
pip install playwright           # uses your installed Chrome, no browser download
make screenshots                 # every screenshot
make screenshots ONLY=reader     # only the reader's: home, reader, card, player, settings, converter or taigi
make screenshots FREQ=TOCFL      # with a frequency list: a file, or the title of one of your library/
```

With `FREQ`, the popup and the card creator show the word's rank. A list of your library is only read (exported to the temporary copy), and the translation models you downloaded are linked into the copy, so that the card creator and Settings › Translation work.

Retake them when a screen changes. To add one, add a step in `tools/screenshots.py` and reference the image from the page: `![What it shows](../assets/screenshots/<name>.png)`.

## License

By contributing, you agree that your contributions are released under the project's [AGPL-3.0-or-later](https://github.com/linlin56/mining-cat/blob/main/LICENSE) license.
