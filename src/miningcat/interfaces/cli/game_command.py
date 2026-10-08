import argparse

from miningcat.infrastructure.hotkeys import DEFAULT_HOTKEY, HOTKEYS
from miningcat.interfaces.cli.command import CONVERT_TARGETS, Command


class GameCommand(Command):
    """Video game / screen share OCR: `game setup` picks the window and its areas, `game serve` captures."""

    name = "game"
    help = "Video game / screen share OCR: push a window's screenshot + OCR'd text to a local web page"

    def configure(self, parser):
        game_sub = parser.add_subparsers(dest="game_command", required=True)
        setup = game_sub.add_parser("setup", help="Select the game window, then its screenshot area and text area")
        setup.add_argument("--window", default=None, metavar="TITLE",
                           help="macOS: pick the first window whose app name or title contains TITLE, instead of asking")
        setup.add_argument("--areas-only", dest="areas_only", action="store_true",
                           help="Keep the saved window, only select the areas again")
        serve = game_sub.add_parser("serve", help="Start capturing and serve the web page (Ctrl+C to stop)")
        self.add_language(serve)
        serve.add_argument("--convert-to", dest="convert_to", default=None, choices=CONVERT_TARGETS,
                           help="Convert the OCR'd text to this Chinese script (e.g. s=Simplified)")
        serve.add_argument("--port", type=int, default=None, help="Web page port (default: 6677)")
        serve.add_argument("--hotkey", default=DEFAULT_HOTKEY, choices=HOTKEYS,
                           help=f"Global key that triggers a capture, even with the game focused (default: {DEFAULT_HOTKEY})")
        serve.add_argument("--continuous", action="store_true",
                           help="Capture continuously, whenever the text changes, instead of with the capture key")
        serve.add_argument("--interval", type=float, default=None,
                           help="Seconds between two looks at the text area in continuous mode (default: 0.5)")
        serve.add_argument("--keep-line-breaks", dest="keep_line_breaks", action="store_true",
                           help="Keep the text's line breaks instead of joining wrapped lines")
        serve.add_argument("--no-browser", dest="no_browser", action="store_true",
                           help="Don't open the web page in the browser")

    def run(self, args: argparse.Namespace) -> None:
        from miningcat.interfaces.cli import game_setup

        game_setup.main(args)
