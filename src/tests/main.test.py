import sys
import argparse
import pytest
from unittest.mock import patch
import main


def test_main_dispatches_audio():
    with patch.object(sys, "argv", ["main.py", "audio"]):
        with patch("main.cmd_audio") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_epub():
    with patch.object(sys, "argv", ["main.py", "epub"]):
        with patch("main.cmd_epub") as mock:
            main.main()
    mock.assert_called_once()


def test_main_no_command_exits():
    with patch.object(sys, "argv", ["main.py"]):
        with pytest.raises(SystemExit):
            main.main()


def test_main_dispatches_align():
    with patch.object(sys, "argv", ["main.py", "align"]):
        with patch("main.cmd_align") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_transcribe():
    with patch.object(sys, "argv", ["main.py", "transcribe"]):
        with patch("main.cmd_transcribe") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_export():
    with patch.object(sys, "argv", ["main.py", "export"]):
        with patch("main.cmd_export") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_convert():
    with patch.object(sys, "argv", ["main.py", "convert", "--source", "tw", "--target", "s"]):
        with patch("main.cmd_convert") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_run():
    with patch.object(sys, "argv", ["main.py", "run"]):
        with patch("main.cmd_run") as mock:
            main.main()
    mock.assert_called_once()


def test_main_dispatches_tts():
    with patch.object(sys, "argv", ["main.py", "tts", "--voice", "TestVoice"]):
        with patch("main.cmd_tts") as mock:
            main.main()
    mock.assert_called_once()


# --- cmd_* function bodies ---

def test_cmd_audio_calls_run():
    args = argparse.Namespace(dry_run=True)
    with patch("audio.run") as mock:
        main.cmd_audio(args)
    mock.assert_called_once_with(dry_run=True)


def test_cmd_epub_calls_run():
    args = argparse.Namespace(list=False, range_str=None, chapters_str=None, preview=False)
    with patch("epub.run") as mock:
        main.cmd_epub(args)
    mock.assert_called_once()


def test_cmd_align_calls_run():
    args = argparse.Namespace(model="tiny", language="mandarin_tw", from_ch=None, only_ch=None)
    with patch("align.run") as mock:
        main.cmd_align(args)
    mock.assert_called_once()


def test_cmd_transcribe_calls_run():
    args = argparse.Namespace(model="tiny", language="japanese", from_ch=None, only_ch=None)
    with patch("align.run_transcribe") as mock:
        main.cmd_transcribe(args)
    mock.assert_called_once()


def test_cmd_tts_calls_run():
    args = argparse.Namespace(voice="zh-TW-HsiaoChenNeural", language="mandarin_tw")
    with patch("tts.run") as mock:
        main.cmd_tts(args)
    mock.assert_called_once()


def test_cmd_export_calls_run():
    args = argparse.Namespace(chapter=None, all=False, preset="ultrafast", language="mandarin_tw")
    with patch("export.run") as mock:
        main.cmd_export(args)
    mock.assert_called_once()


def test_cmd_convert_calls_convert():
    args = argparse.Namespace(source="tw", target="s")
    with patch("chinese_converter.convert_srt_dir") as mock:
        main.cmd_convert(args)
    mock.assert_called_once_with("tw", "s")


def test_cmd_run_calls_all_steps():
    args = argparse.Namespace(range_str=None)
    with patch("audio.run") as m_audio, \
         patch("epub.run") as m_epub, \
         patch("align.run") as m_align, \
         patch("export.run") as m_export:
        main.cmd_run(args)
    m_audio.assert_called_once()
    m_epub.assert_called_once()
    m_align.assert_called_once()
    m_export.assert_called_once_with(all_chapters=True)
