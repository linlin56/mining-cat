import argparse
import sys

from miningcat.application import updates as app_updates
from miningcat.infrastructure.system import updates
from miningcat.interfaces.cli.command import Command


class UpdateCommand(Command):
    """Updates MiningCat to the newest commit of main whose tests passed, and installs the packages that changed."""

    name, help = "update", "Update MiningCat (the newest version whose tests passed)"

    def configure(self, parser):
        parser.add_argument("--check", action="store_true", help="only tell whether an update is available")

    def run(self, args):
        if args.check:
            check = updates.check()
            for line in app_updates.describe(check, changes=True):
                print(line)
            if check.error:  # failed this time: exit code 1, as the update
                sys.exit(1)
            return
        outcome = app_updates.update_now()
        # Updates off isn't a failure (`make update && make gui` goes on), an update that failed is (already told).
        if outcome.outcome in (app_updates.Outcome.FAILED, app_updates.Outcome.INSTALL_FAILED):
            sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """`python -m miningcat update`, without the rest of the CLI (see miningcat/__main__.py)."""
    command = UpdateCommand()
    parser = argparse.ArgumentParser(prog="python -m miningcat update", description=command.help)
    command.configure(parser)
    command.run(parser.parse_args(argv))
