import argparse
import os

from miningcat.interfaces.web.app import main as run_server

DEFAULT_PORT = int(os.environ.get("MININGCAT_PORT", "5050"))


def main() -> None:
    parser = argparse.ArgumentParser(description="MiningCat web GUI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"local port (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--reader", action="store_true", help="open the ebook reader instead of the converter")
    parser.add_argument("--player", action="store_true", help="open the video player instead of the converter")
    args = parser.parse_args()
    page = "reader/" if args.reader else "player/" if args.player else ""
    run_server(port=args.port, open_browser=not args.no_browser, page=page)


if __name__ == "__main__":
    main()
