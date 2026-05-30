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
    from language import Language
    align.run(
        model_name=args.model,
        language=Language.from_id(args.language),
        from_ch=args.from_ch,
        only_ch=args.only_ch,
    )


# Used if no ebook is provided, will generate segments based on audio alone (no alignment, just transcription).
# It's not as accurate but great if you don't have the ebook.
def cmd_transcribe(args: argparse.Namespace) -> None:
    import align
    from language import Language
    align.run_transcribe(
        model_name=args.model,
        language=Language.from_id(args.language),
        from_ch=args.from_ch,
        only_ch=args.only_ch,
    )


def cmd_tts(args: argparse.Namespace) -> None:
    import tts
    tts.run(voice=args.voice)


def cmd_export(args: argparse.Namespace) -> None:
    import export
    export.run(
        chapter_num=args.chapter,
        all_chapters=args.all,
        preset=args.preset,
    )


def cmd_convert(args: argparse.Namespace) -> None:
    import chinese_converter
    chinese_converter.convert_srt_dir(args.source, args.target)


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
    p_align.add_argument("--language", default="mandarin_tw",
                         choices=["mandarin_tw", "mandarin_cn"])
    p_align.add_argument("--from", dest="from_ch", type=int, default=None,
                         help="Start from chapter N")
    p_align.add_argument("--only", dest="only_ch", type=int, default=None,
                         help="Process only chapter N")

    # transcribe
    p_transcribe = sub.add_parser("transcribe", help="Whisper transcription (no epub alignment)")
    p_transcribe.add_argument("--model", default="tiny",
                              choices=["tiny", "base", "small", "medium", "large"])
    p_transcribe.add_argument("--language", default="mandarin_tw",
                              choices=["mandarin_tw", "mandarin_cn"])
    p_transcribe.add_argument("--from", dest="from_ch", type=int, default=None,
                              help="Start from chapter N")
    p_transcribe.add_argument("--only", dest="only_ch", type=int, default=None,
                              help="Process only chapter N")

    # tts
    p_tts = sub.add_parser("tts", help="Generate audio from EPUB text using edge-tts")
    p_tts.add_argument("--voice", required=True, help="Edge-TTS voice name (e.g. zh-TW-HsiaoChenNeural)")

    # export
    p_export = sub.add_parser("export", help="Render final MP4 files")
    p_export.add_argument("--chapter", type=int, default=None)
    p_export.add_argument("--all", action="store_true")
    p_export.add_argument("--preset", default="ultrafast",
                          choices=["ultrafast", "superfast", "veryfast",
                                   "faster", "fast", "medium"])

    # convert
    p_convert = sub.add_parser("convert", help="Convert SRT character script with OpenCC")
    p_convert.add_argument("--source", required=True, choices=["s", "tw"],
                           help="Source script (s=Simplified, tw=Traditional Taiwan)")
    p_convert.add_argument("--target", required=True, choices=["s", "tw", "t", "hk"],
                           help="Target script")

    # run
    p_run = sub.add_parser("run", help="Run all steps in sequence")
    p_run.add_argument("--range", dest="range_str", metavar="A-B",
                       help="Epub chapter range (e.g. 4-9)")

    args = parser.parse_args()

    dispatch = {
        "audio":      cmd_audio,
        "epub":       cmd_epub,
        "align":      cmd_align,
        "transcribe": cmd_transcribe,
        "tts":        cmd_tts,
        "convert":    cmd_convert,
        "export":     cmd_export,
        "run":        cmd_run,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
