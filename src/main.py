import argparse
import sys

from game_ocr.hotkey import DEFAULT_HOTKEY, HOTKEYS
from language import Language
from ocr_mining.frames import OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN


# Whisper sizes, and Qwen3-ASR's for the languages it transcribes (Taigi: a Whisper size picks one of them too).
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large", "turbo", "qwen3-0.6b", "qwen3-1.7b"]
# Chinese scripts (s=Simplified, tw/t/hk=Traditional), and Taigi's writing systems.
CONVERT_TARGETS = ["s", "tw", "t", "hk", "hanji", "tailo", "poj"]


def _parse_ocr_region(value: str) -> tuple[float, float, float, float]:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--ocr-region must be 4 comma-separated fractions: x,y,w,h")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError("--ocr-region values must be numbers")
    if not all(0.0 <= v <= 1.0 for v in (x, y, w, h)):
        raise argparse.ArgumentTypeError("--ocr-region values must be fractions between 0 and 1")
    return (x, y, w, h)


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
    tts.run(voice=args.voice, lang=Language.from_id(args.language))


def cmd_export(args: argparse.Namespace) -> None:
    import export
    lang = Language.from_id(args.language)
    export.run(
        chapter_num=args.chapter,
        all_chapters=args.all,
        preset=args.preset,
        subtitle_lang=lang.value.iso639_2,
    )


def cmd_convert(args: argparse.Namespace) -> None:
    import chinese_converter
    chinese_converter.convert_srt_dir(args.source, args.target)


def cmd_video(args: argparse.Namespace) -> None:
    import video
    video.run(
        url=args.url,
        model_name=args.model,
        language=Language.from_id(args.language),
        app_id=args.app_id,
        convert_target=args.convert_to,
        video_path=args.video_path,
        audio_track=args.audio_track,
        use_ocr=args.ocr,
        ocr_region=args.ocr_region,
        ocr_fps=args.ocr_fps,
    )


def cmd_game(args: argparse.Namespace) -> None:
    from game_ocr import cli
    cli.main(args)


def cmd_run(args: argparse.Namespace) -> None:
    import audio
    import epub
    import align
    import export

    print("=== Step 1: audio ===")
    audio.run()

    print("\n=== Step 2: ebook ===")
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
                         choices=MODEL_CHOICES)
    p_align.add_argument("--language", default="mandarin_tw",
                         choices=Language.ids())
    p_align.add_argument("--from", dest="from_ch", type=int, default=None,
                         help="Start from chapter N")
    p_align.add_argument("--only", dest="only_ch", type=int, default=None,
                         help="Process only chapter N")

    # transcribe
    p_transcribe = sub.add_parser("transcribe", help="Whisper transcription (no epub alignment)")
    p_transcribe.add_argument("--model", default="tiny",
                              choices=MODEL_CHOICES)
    p_transcribe.add_argument("--language", default="mandarin_tw",
                              choices=Language.ids())
    p_transcribe.add_argument("--from", dest="from_ch", type=int, default=None,
                              help="Start from chapter N")
    p_transcribe.add_argument("--only", dest="only_ch", type=int, default=None,
                              help="Process only chapter N")

    # tts
    p_tts = sub.add_parser("tts", help="Generate audio from EPUB text using edge-tts (or a local voice)")
    p_tts.add_argument("--voice", required=True,
                       help="Edge-TTS voice name (e.g. zh-TW-HsiaoChenNeural), or nan-TW-MmsTaigi for Taigi (local)")
    p_tts.add_argument("--language", default="mandarin_tw", choices=Language.ids())

    # export
    p_export = sub.add_parser("export", help="Render final MP4 files")
    p_export.add_argument("--chapter", type=int, default=None)
    p_export.add_argument("--all", action="store_true")
    p_export.add_argument("--language", default="mandarin_tw",
                          choices=Language.ids())
    p_export.add_argument("--preset", default="ultrafast",
                          choices=["ultrafast", "superfast", "veryfast",
                                   "faster", "fast", "medium"])

    # convert
    p_convert = sub.add_parser("convert", help="Convert SRT character script with OpenCC, or Taigi's writing system")
    p_convert.add_argument("--source", required=True, choices=["s", "tw", "hk", "nan"],
                           help="Source script (s=Simplified, tw=Traditional Taiwan, hk=Hong Kong, nan=any Taigi text)")
    p_convert.add_argument("--target", required=True, choices=CONVERT_TARGETS,
                           help="Target script (Taigi: hanji, tailo or poj)")

    # run
    p_run = sub.add_parser("run", help="Run all steps in sequence")
    p_run.add_argument("--range", dest="range_str", metavar="A-B",
                       help="Epub chapter range (e.g. 4-9)")

    # video
    p_video = sub.add_parser("video", help="Download an online video or use a local video file, and generate subtitles")
    video_source = p_video.add_mutually_exclusive_group(required=True)
    video_source.add_argument("--url", help="Video URL (e.g. Instagram reel)")
    video_source.add_argument("--file", dest="video_path", help="Path to a local video file")
    p_video.add_argument("--model", default="tiny",
                         choices=MODEL_CHOICES)
    p_video.add_argument("--language", default="mandarin_tw",
                         choices=Language.ids())
    p_video.add_argument("--app-id", dest="app_id", default="web",
                         help="Instagram X-IG-App-ID (numeric id, 'ios', or 'web')")
    p_video.add_argument("--convert-to", dest="convert_to", default=None,
                         choices=CONVERT_TARGETS,
                         help="Convert the generated SRT to this script (e.g. s=Simplified)")
    p_video.add_argument("--audio-track", dest="audio_track", type=int, default=None,
                         help="Index of the audio track to transcribe, if the video has several (0-based)")
    p_video.add_argument("--ocr", action="store_true",
                         help="Use OCR on burned-in subtitles instead of Whisper (skips audio extraction/transcription)")
    p_video.add_argument("--ocr-region", dest="ocr_region", type=_parse_ocr_region, default=None,
                         metavar="X,Y,W,H", help="Normalized subtitle region as fractions 0-1 (default: bottom third)")
    p_video.add_argument("--ocr-fps", dest="ocr_fps", type=int, default=OCR_FPS_DEFAULT,
                         choices=range(OCR_FPS_MIN, OCR_FPS_MAX + 1), metavar=f"[{OCR_FPS_MIN}-{OCR_FPS_MAX}]",
                         help=f"OCR frame sampling rate in frames/second (default: {OCR_FPS_DEFAULT})")

    # game
    p_game = sub.add_parser("game", help="Video game / screen share OCR: push a window's screenshot + OCR'd text to a local web page")
    game_sub = p_game.add_subparsers(dest="game_command", required=True)
    p_game_setup = game_sub.add_parser("setup", help="Select the game window, then its screenshot area and text area")
    p_game_setup.add_argument("--window", default=None, metavar="TITLE",
                              help="macOS: pick the first window whose app name or title contains TITLE, instead of asking")
    p_game_setup.add_argument("--areas-only", dest="areas_only", action="store_true",
                              help="Keep the saved window, only select the areas again")
    p_game_serve = game_sub.add_parser("serve", help="Start capturing and serve the web page (Ctrl+C to stop)")
    p_game_serve.add_argument("--language", default="mandarin_tw", choices=Language.ids())
    p_game_serve.add_argument("--convert-to", dest="convert_to", default=None, choices=CONVERT_TARGETS,
                              help="Convert the OCR'd text to this Chinese script (e.g. s=Simplified)")
    p_game_serve.add_argument("--port", type=int, default=None, help="Web page port (default: 6677)")
    p_game_serve.add_argument("--hotkey", default=DEFAULT_HOTKEY, choices=HOTKEYS,
                              help=f"Global key that triggers a capture, even with the game focused (default: {DEFAULT_HOTKEY})")
    p_game_serve.add_argument("--continuous", action="store_true",
                              help="Capture continuously, whenever the text changes, instead of with the capture key")
    p_game_serve.add_argument("--interval", type=float, default=None,
                              help="Seconds between two looks at the text area in continuous mode (default: 0.5)")
    p_game_serve.add_argument("--keep-line-breaks", dest="keep_line_breaks", action="store_true",
                              help="Keep the text's line breaks instead of joining wrapped lines")
    p_game_serve.add_argument("--no-browser", dest="no_browser", action="store_true",
                              help="Don't open the web page in the browser")

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
        "video":      cmd_video,
        "game":       cmd_game,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
