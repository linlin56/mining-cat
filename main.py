# main.py — Audiobook-to-subtitles pipeline.
#
# Subcommands:
#   audio   Prepare audio chapters (copy MP3s or split .m4b)
#   epub    Extract epub text split by chapter
#   align   Forced alignment of chapter text to audio
#   export  Render final MP4 files
#   run     Run all steps in sequence
#
# Usage:
#   python main.py audio [--dry-run]
#   python main.py epub [--list] [--range 4-9] [--chapters 3,4,5] [--preview]
#   python main.py align [--model tiny] [--language zh] [--from 3] [--only 1]
#   python main.py export [--chapter 5] [--all] [--preset ultrafast]
#   python main.py run [--range 4-9]

import argparse
import sys


def cmd_audio(args: argparse.Namespace) -> None:
    import audio
    audio.run(dry_run=args.dry_run)


def cmd_epub(args: argparse.Namespace) -> None:
    import epub
    epub.run(
        list_only=args.list,
        range_str=args.range_str,
        chapters_str=args.chapters_str,
        preview=args.preview,
    )


def cmd_align(args: argparse.Namespace) -> None:
    import align
    align.run(
        model_name=args.model,
        language=args.language,
        from_ch=args.from_ch,
        only_ch=args.only_ch,
    )


def cmd_export(args: argparse.Namespace) -> None:
    import export
    export.run(
        chapter_num=args.chapter,
        all_chapters=args.all,
        preset=args.preset,
    )


def cmd_run(args: argparse.Namespace) -> None:
    import audio
    import epub
    import align
    import export

    print("=== Step 1: audio ===")
    audio.run()

    print("\n=== Step 2: epub ===")
    epub.run(range_str=args.range_str)

    print("\n=== Step 3: align ===")
    align.run()

    print("\n=== Step 4: export ===")
    export.run(all_chapters=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Audiobook-to-subtitles pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # audio
    p_audio = sub.add_parser("audio", help="Prepare audio chapters")
    p_audio.add_argument("--dry-run", action="store_true",
                         help="Show detected chapters without extracting")

    # epub
    p_epub = sub.add_parser("epub", help="Extract epub text split by chapter")
    p_epub.add_argument("--list", action="store_true",
                        help="List chapters without extracting")
    p_epub.add_argument("--range", dest="range_str", metavar="A-B",
                        help="Extract only chapters A to B (e.g. 4-9)")
    p_epub.add_argument("--chapters", dest="chapters_str", metavar="N,M,...",
                        help="Manual selection (e.g. 3,4,5)")
    p_epub.add_argument("--preview", action="store_true",
                        help="Print a text excerpt for each chapter")

    # align
    p_align = sub.add_parser("align", help="Forced alignment of chapter text to audio")
    p_align.add_argument("--model", default="tiny",
                         choices=["tiny", "base", "small", "medium", "large"])
    p_align.add_argument("--language", default="zh")
    p_align.add_argument("--from", dest="from_ch", type=int, default=None,
                         help="Start from chapter N")
    p_align.add_argument("--only", dest="only_ch", type=int, default=None,
                         help="Process only chapter N")

    # export
    p_export = sub.add_parser("export", help="Render final MP4 files")
    p_export.add_argument("--chapter", type=int, default=None)
    p_export.add_argument("--all", action="store_true")
    p_export.add_argument("--preset", default="ultrafast",
                          choices=["ultrafast", "superfast", "veryfast",
                                   "faster", "fast", "medium"])

    # run
    p_run = sub.add_parser("run", help="Run all steps in sequence")
    p_run.add_argument("--range", dest="range_str", metavar="A-B",
                       help="Epub chapter range (e.g. 4-9)")

    args = parser.parse_args()

    dispatch = {
        "audio":  cmd_audio,
        "epub":   cmd_epub,
        "align":  cmd_align,
        "export": cmd_export,
        "run":    cmd_run,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
