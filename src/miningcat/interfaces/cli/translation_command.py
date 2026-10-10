from tqdm import tqdm

from miningcat.application.converter.errors import ConverterError
from miningcat.infrastructure.translation import install
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.interfaces.cli.command import Command


class TranslationInstallCommand(Command):
    """Installs a translation model (NLLB-200 or Qwen3): the packages of its engine, then the model."""

    name, help = "install-translation", "Install a model translating sentences and subtitles (NLLB-200 or Qwen3)"

    def configure(self, parser):
        parser.add_argument("--model", default=install.DEFAULT_MODEL, choices=list(install.MODELS))

    def run(self, args):
        label = install.MODELS[args.model].label
        with tqdm(unit="B", unit_scale=True, desc=label) as bar:
            def progress(done, total):
                bar.total = total
                bar.update(done - bar.n)

            try:
                returncode = install.install(args.model, progress)
            except TranslateError as exc:
                raise ConverterError(str(exc))
        if returncode != 0:
            raise ConverterError("The install failed: see pip's output above.")
        print(f"{label} is installed: choose it in Settings › Translation.")
