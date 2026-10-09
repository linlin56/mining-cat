# Contributing

The full contributor guide is on the [documentation site](https://linlin56.github.io/mining-cat/how-to-contribute/)
(and in [`docs/how-to-contribute/`](docs/how-to-contribute/)):

- [Project structure](docs/how-to-contribute/project-structure.md): the layers of the `miningcat` package and where things are;
- [Add a language](docs/how-to-contribute/add-language.md): a new member of the `Language` enum, built with a `LanguageProfileBuilder`;
- [Add a video platform](docs/how-to-contribute/add-video-platform.md): a new `VideoHandler`;
- [Add a capture backend](docs/how-to-contribute/add-capture-backend.md): video game capture on another OS.

## In short

```bash
make install        # dependencies
make test           # the tests (the CI also requires 80% coverage: `make coverage`)
make gui            # the web GUI, at http://127.0.0.1:5050/
cd src && python -m miningcat --help    # the CLI
```

- The code lives in `src/miningcat/`, in four layers: `domain` (pure code), `infrastructure` (adapters to the outside
  world), `application` (use cases) and `interfaces` (CLI, web GUI). A layer only imports the layers below it:
  `src/tests/architecture.test.py` checks it.
- Tests live in `src/tests/`, in folders mirroring the layers. They never touch the network nor your own files.
- Priority goes to languages supported by Whisper and edge-tts. Languages can be added by people who don't speak them,
  but please ask a native speaker to double-check, and say so in your pull request.
