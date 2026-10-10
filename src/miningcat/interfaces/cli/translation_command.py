from tqdm import tqdm

from miningcat.application.converter.errors import ConverterError
from miningcat.infrastructure.translation import nllb_install
from miningcat.infrastructure.translation.errors import TranslateError
from miningcat.infrastructure.translation.nllb import DEFAULT_MODEL, MODELS
from miningcat.interfaces.cli.command import Command


class NllbInstallCommand(Command):
    """Installs NLLB-200 (optional instead of Argos Translate): its packages, then the model asked for."""

    name, help = "install-nllb", "Install NLLB-200 for translations (optional instead of Argos Translate)"

    def configure(self, parser):
        parser.add_argument("--model", default=DEFAULT_MODEL, choices=list(MODELS))

    def run(self, args):
        with tqdm(unit="B", unit_scale=True, desc=MODELS[args.model].label) as bar:
            def progress(done, total):
                bar.total = total
                bar.update(done - bar.n)

            try:
                returncode = nllb_install.install(args.model, progress)
            except TranslateError as exc:
                raise ConverterError(str(exc))
        if returncode != 0:
            raise ConverterError("The install failed: see pip's output above.")
        print(f"{MODELS[args.model].label} is installed: choose it in Settings › Translation.")
