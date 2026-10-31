"""The server's process, started by __main__.py (which updates MiningCat at launch, and installs the packages of an
update made from the home page between two servers). Its exit code tells why it stopped (jobs.ServerEnd)."""
import argparse
import os
import sys

from miningcat.infrastructure.system.updates import UpdateCheck
from miningcat.interfaces.web.app import main as run_server
from miningcat.interfaces.web.process import UP_TO_DATE_ENV, WATCH_PARENT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MiningCat web GUI's server")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--page", default="")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(WATCH_PARENT, action="store_true")
    args = parser.parse_args(argv)
    check = UpdateCheck() if os.environ.get(UP_TO_DATE_ENV) else None
    return run_server(port=args.port, open_browser=not args.no_browser, page=args.page, update_check=check,
                      with_parent=args.watch_parent).value


if __name__ == "__main__":
    sys.exit(main())
