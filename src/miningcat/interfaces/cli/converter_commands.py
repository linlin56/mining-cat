"""The steps of the converter, run one by one (the GUI runs them as subprocesses), or all at once."""
import argparse

from miningcat.application.converter import video_subtitles
from miningcat.application.converter.steps import (
    audio_preparation,
    ebook_extraction,
    mp4_export,
    script_conversion,
    speech_synthesis,
)
from miningcat.application.converter.steps.subtitles import Alignment, Transcription
from miningcat.application.converter.video_request import VideoRequestBuilder
from miningcat.domain.languages import Language
from miningcat.domain.ocr.regions import valid_region
from miningcat.domain.ocr.sampling import OCR_FPS_DEFAULT, OCR_FPS_MAX, OCR_FPS_MIN
from miningcat.interfaces.cli.command import CHINESE_SCRIPTS, Command


def parse_ocr_region(value: str) -> tuple[float, float, float, float]:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--ocr-region must be 4 comma-separated fractions: x,y,w,h")
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError("--ocr-region values must be numbers")
    try:
        return valid_region(numbers)
    except ValueError:
        raise argparse.ArgumentTypeError("--ocr-region values must be fractions between 0 and 1")


def _add_chapter_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="from_ch", type=int, default=None, help="Start from chapter N")
    parser.add_argument("--only", dest="only_ch", type=int, default=None, help="Process only chapter N")


class AudioCommand(Command):
    name, help = "audio", "Prepare audio chapters"

    def configure(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show detected chapters without extracting")

    def run(self, args):
        audio_preparation.run(dry_run=args.dry_run)


class EpubCommand(Command):
    name, help = "epub", "Extract epub text split by chapter"

    def configure(self, parser):
        parser.add_argument("--list", action="store_true", help="List chapters without extracting")
        parser.add_argument("--range", dest="range_str", metavar="A-B", help="Extract only chapters A to B (e.g. 4-9)")
        parser.add_argument("--chapters", dest="chapters_str", metavar="N,M,...", help="Manual selection (e.g. 3,4,5)")
        parser.add_argument("--preview", action="store_true", help="Print a text excerpt for each chapter")

    def run(self, args):
        ebook_extraction.run(list_only=args.list, range_str=args.range_str, chapters_str=args.chapters_str,
                             preview=args.preview)


class AlignCommand(Command):
    name, help = "align", "Forced alignment of chapter text to audio"

    def configure(self, parser):
        self.add_model(parser)
        self.add_language(parser)
        _add_chapter_options(parser)

    def run(self, args):
        Alignment(args.model, Language.from_id(args.language), args.from_ch, args.only_ch).run()


class TranscribeCommand(Command):
    """Subtitles from the audio alone, without the book: less accurate, but needs no ebook."""

    name, help = "transcribe", "Whisper transcription (no epub alignment)"

    def configure(self, parser):
        self.add_model(parser)
        self.add_language(parser)
        _add_chapter_options(parser)

    def run(self, args):
        Transcription(args.model, Language.from_id(args.language), args.from_ch, args.only_ch).run()


class TtsCommand(Command):
    name, help = "tts", "Generate audio from EPUB text using edge-tts"

    def configure(self, parser):
        parser.add_argument("--voice", required=True, help="Edge-TTS voice name (e.g. zh-TW-HsiaoChenNeural)")
        self.add_language(parser)

    def run(self, args):
        speech_synthesis.run(voice=args.voice, lang=Language.from_id(args.language))


class ExportCommand(Command):
    name, help = "export", "Render final MP4 files"

    def configure(self, parser):
        parser.add_argument("--chapter", type=int, default=None)
        parser.add_argument("--all", action="store_true")
        self.add_language(parser)
        parser.add_argument("--preset", default="ultrafast",
                            choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"])

    def run(self, args):
        mp4_export.run(chapter_num=args.chapter, all_chapters=args.all, preset=args.preset,
                       subtitle_lang=Language.from_id(args.language).profile.iso639_2)


class ConvertCommand(Command):
    name, help = "convert", "Convert SRT character script with OpenCC"

    def configure(self, parser):
        parser.add_argument("--source", required=True, choices=["s", "tw"],
                            help="Source script (s=Simplified, tw=Traditional Taiwan)")
        parser.add_argument("--target", required=True, choices=CHINESE_SCRIPTS, help="Target script")

    def run(self, args):
        script_conversion.convert_srt_dir(args.source, args.target)


class RunCommand(Command):
    name, help = "run", "Run all steps in sequence"

    def configure(self, parser):
        parser.add_argument("--range", dest="range_str", metavar="A-B", help="Epub chapter range (e.g. 4-9)")

    def run(self, args):
        print("=== Step 1: audio ===")
        audio_preparation.run()
        print("\n=== Step 2: ebook ===")
        ebook_extraction.run(range_str=args.range_str)
        print("\n=== Step 3: align ===")
        Alignment().run()
        print("\n=== Step 4: export ===")
        mp4_export.run(all_chapters=True)


class VideoCommand(Command):
    name, help = "video", "Download an online video or use a local video file, and generate subtitles"

    def configure(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--url", help="Video URL (e.g. Instagram reel)")
        source.add_argument("--file", dest="video_path", help="Path to a local video file")
        self.add_model(parser)
        self.add_language(parser)
        parser.add_argument("--app-id", dest="app_id", default="web",
                            help="Instagram X-IG-App-ID (numeric id, 'ios', or 'web')")
        parser.add_argument("--convert-to", dest="convert_to", default=None, choices=CHINESE_SCRIPTS,
                            help="Convert the generated SRT to this script (e.g. s=Simplified)")
        parser.add_argument("--audio-track", dest="audio_track", type=int, default=None,
                            help="Index of the audio track to transcribe, if the video has several (0-based)")
        parser.add_argument("--ocr", action="store_true",
                            help="Use OCR on burned-in subtitles instead of Whisper (skips audio extraction/transcription)")
        parser.add_argument("--ocr-region", dest="ocr_region", type=parse_ocr_region, default=None,
                            metavar="X,Y,W,H", help="Normalized subtitle region as fractions 0-1 (default: bottom third)")
        parser.add_argument("--ocr-fps", dest="ocr_fps", type=int, default=OCR_FPS_DEFAULT,
                            choices=range(OCR_FPS_MIN, OCR_FPS_MAX + 1), metavar=f"[{OCR_FPS_MIN}-{OCR_FPS_MAX}]",
                            help=f"OCR frame sampling rate in frames/second (default: {OCR_FPS_DEFAULT})")

    @staticmethod
    def request(args):
        builder = VideoRequestBuilder(Language.from_id(args.language)).whisper(args.model).convert_to(args.convert_to)
        if args.video_path is not None:
            builder.local_file(args.video_path, args.audio_track)
        else:
            builder.url(args.url, app_id=args.app_id)
        if args.ocr:
            builder.ocr(args.ocr_region, args.ocr_fps)
        return builder.build()

    def run(self, args):
        video_subtitles.run(self.request(args))


CONVERTER_COMMANDS: list[Command] = [
    AudioCommand(), EpubCommand(), AlignCommand(), TranscribeCommand(), TtsCommand(), ExportCommand(),
    ConvertCommand(), RunCommand(), VideoCommand(),
]
