from unittest.mock import patch

import pytest

from miningcat.application.converter.errors import ConverterError
from miningcat.interfaces.cli import converter_commands as commands
from miningcat.interfaces.cli.game_command import GameCommand
from miningcat.interfaces.cli.main import COMMANDS, build_parser, main


def command(name: str):
    return next(c for c in COMMANDS if c.name == name)


@pytest.mark.parametrize("argv", [
    ["audio"], ["epub"], ["align"], ["transcribe"], ["export"], ["run"],
    ["convert", "--source", "tw", "--target", "s"],
    ["tts", "--voice", "TestVoice"],
    ["video", "--url", "https://www.instagram.com/reel/xxx/"],
    ["video", "--file", "/tmp/movie.mp4"],
    ["game", "serve"],
])
def test_main_dispatches_to_the_command(argv):
    with patch.object(type(command(argv[0])), "run") as run:
        main(argv)
    run.assert_called_once()
    assert run.call_args[0][0].command == argv[0]


@pytest.mark.parametrize("argv", [
    [],
    ["game"],
    ["game", "serve", "--hotkey", "F13"],
    ["video"],
    ["video", "--url", "https://www.instagram.com/reel/xxx/", "--file", "/tmp/movie.mp4"],
    ["video", "--file", "/tmp/movie.mp4", "--ocr", "--ocr-region", "not,a,region"],
    ["video", "--file", "/tmp/movie.mp4", "--ocr", "--ocr-region", "0,0,1,1.5"],
    ["video", "--file", "/tmp/movie.mp4", "--ocr", "--ocr-fps", "13"],
])
def test_invalid_command_lines_exit(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_game_serve_options():
    args = build_parser().parse_args(["game", "serve", "--language", "japanese", "--continuous"])
    assert (args.game_command, args.language, args.continuous) == ("serve", "japanese", True)
    args = build_parser().parse_args(["game", "serve"])
    assert (args.hotkey, args.continuous) == ("F9", False)
    assert build_parser().parse_args(["game", "setup", "--window", "Sample Quest"]).window == "Sample Quest"


def test_game_command_delegates_to_game_setup():
    args = build_parser().parse_args(["game", "serve"])
    with patch("miningcat.interfaces.cli.game_setup.main") as game_main:
        GameCommand().run(args)
    game_main.assert_called_once_with(args)


def test_converter_errors_exit_with_code_1(capsys):
    with patch.object(commands.audio_preparation, "run", side_effect=ConverterError("No audio file")):
        with pytest.raises(SystemExit) as exit_info:
            main(["audio"])
    assert exit_info.value.code == 1
    assert "Error: No audio file" in capsys.readouterr().out


@pytest.mark.parametrize("argv,module,function,expected", [
    (["audio", "--dry-run"], "audio_preparation", "run", {"dry_run": True}),
    (["epub", "--range", "4-9"], "ebook_extraction", "run", {"range_str": "4-9"}),
    (["export", "--all", "--language", "french"], "mp4_export", "run", {"all_chapters": True, "subtitle_lang": "fra"}),
    (["tts", "--voice", "V", "--language", "japanese"], "speech_synthesis", "run", {"voice": "V"}),
])
def test_converter_steps_get_their_options(argv, module, function, expected):
    with patch.object(getattr(commands, module), function) as step:
        main(argv)
    for key, value in expected.items():
        assert step.call_args.kwargs[key] == value


def test_convert_converts_the_subtitles():
    with patch.object(commands.script_conversion, "convert_srt_dir") as convert:
        main(["convert", "--source", "tw", "--target", "s"])
    convert.assert_called_once_with("tw", "s")


@pytest.mark.parametrize("name,cls", [("align", "Alignment"), ("transcribe", "Transcription")])
def test_subtitle_steps(name, cls):
    with patch.object(commands, cls) as step:
        main([name, "--language", "japanese", "--only", "2", "--model", "small"])
    args = step.call_args[0]
    assert args[0] == "small" and args[1].id == "japanese" and args[3] == 2
    step.return_value.run.assert_called_once()


def test_run_runs_every_step():
    with patch.object(commands.audio_preparation, "run") as audio, \
         patch.object(commands.ebook_extraction, "run") as ebook, \
         patch.object(commands, "Alignment") as alignment, \
         patch.object(commands.mp4_export, "run") as export:
        main(["run", "--range", "1-2"])
    audio.assert_called_once()
    ebook.assert_called_once_with(range_str="1-2")
    alignment.return_value.run.assert_called_once()
    export.assert_called_once_with(all_chapters=True)


def video_request(*argv):
    with patch.object(commands.video_subtitles, "run") as run:
        main(["video", *argv])
    return run.call_args[0][0]


def test_video_url():
    request = video_request("--url", "https://www.instagram.com/reel/xxx/", "--convert-to", "s", "--app-id", "ios")
    assert request.url == "https://www.instagram.com/reel/xxx/" and request.app_id == "ios"
    assert request.convert_target == "s" and request.video_path is None and not request.use_ocr


def test_video_local_file_and_audio_track():
    request = video_request("--file", "/tmp/movie.mp4", "--audio-track", "2", "--model", "small")
    assert str(request.video_path) == "/tmp/movie.mp4" and request.audio_track == 2 and request.model_name == "small"


def test_video_ocr_options():
    request = video_request("--file", "/tmp/movie.mp4", "--ocr", "--ocr-region", "0,0.5,1,0.5", "--ocr-fps", "8")
    assert request.use_ocr and request.ocr_region == (0.0, 0.5, 1.0, 0.5) and request.ocr_fps == 8
    assert video_request("--file", "/tmp/movie.mp4", "--ocr").ocr_fps == 4
