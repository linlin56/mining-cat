import argparse
import sys

from miningcat.application.converter.errors import ConverterError
from miningcat.interfaces.cli.command import Command
from miningcat.interfaces.cli.converter_commands import CONVERTER_COMMANDS
from miningcat.interfaces.cli.game_command import GameCommand
from miningcat.interfaces.cli.translation_command import NllbInstallCommand

COMMANDS: list[Command] = [*CONVERTER_COMMANDS, GameCommand(), NllbInstallCommand()]


def build_parser(commands: list[Command] = COMMANDS) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m miningcat", description="MiningCat: audiobook, video and game "
                                     "to mineable material")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in commands:
        command.configure(sub.add_parser(command.name, help=command.help))
    return parser


def main(argv: list[str] | None = None, commands: list[Command] = COMMANDS) -> None:
    args = build_parser(commands).parse_args(argv)
    command = next(c for c in commands if c.name == args.command)
    try:
        command.run(args)
    except ConverterError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
