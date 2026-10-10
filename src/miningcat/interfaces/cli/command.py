import argparse
from abc import ABC, abstractmethod

from miningcat.domain.languages import Language

# Whisper sizes, and Qwen3-ASR's (optional, for the languages it knows; for Taigi a Whisper size picks one of them).
SPEECH_MODELS = ["tiny", "base", "small", "medium", "large", "turbo", "qwen3-0.6b", "qwen3-1.7b"]
# Chinese scripts (s=Simplified, tw/t/hk=Traditional), and Taigi's writing systems.
CONVERT_TARGETS = ["s", "tw", "t", "hk", "hanji", "tailo", "poj"]
DEFAULT_LANGUAGE = "mandarin_tw"


class Command(ABC):
    """A subcommand of the CLI: its arguments, and what it runs."""

    name: str
    help: str

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Adds the command's arguments."""

    @abstractmethod
    def run(self, args: argparse.Namespace) -> None:
        """Runs the command. A ConverterError is shown as an error, with exit code 1."""

    @staticmethod
    def add_language(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--language", default=DEFAULT_LANGUAGE, choices=Language.ids())

    @staticmethod
    def add_model(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--model", default="tiny", choices=SPEECH_MODELS)
