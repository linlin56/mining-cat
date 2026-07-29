from pathlib import Path
from unittest.mock import MagicMock, patch

from gui_components import pipeline
from language import Language


# _find_video_srt
def test_find_video_srt_prefers_whisper_over_ocr_and_source(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc_ocr.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc_whisper.srt").write_text("1\n", encoding="utf-8")
    assert pipeline._find_video_srt(tmp_path) == tmp_path / "abc_whisper.srt"


def test_find_video_srt_falls_back_to_ocr_when_no_whisper(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    (tmp_path / "abc_ocr.srt").write_text("1\n", encoding="utf-8")
    assert pipeline._find_video_srt(tmp_path) == tmp_path / "abc_ocr.srt"


def test_find_video_srt_falls_back_to_any_srt(tmp_path):
    (tmp_path / "abc_source.srt").write_text("1\n", encoding="utf-8")
    assert pipeline._find_video_srt(tmp_path) == tmp_path / "abc_source.srt"


def test_find_video_srt_none_when_directory_empty(tmp_path):
    assert pipeline._find_video_srt(tmp_path) is None


# run_video_pipeline - cmd_args threading
def _run_and_capture_cmd_args(**overrides) -> list[str]:
    captured = {}

    def fake_run_cmd(args, *, schedule, log):
        captured["args"] = args
        return 0

    kwargs = dict(
        python_exe="python3",
        lang=Language.FRENCH,
        model="tiny",
        convert_target=None,
        video_path=Path("/tmp/movie.mp4"),
        schedule=lambda delay, fn, *a: fn(*a),
        log=MagicMock(),
        set_status=MagicMock(),
        on_done=MagicMock(),
        on_finish=MagicMock(),
    )
    kwargs.update(overrides)

    with patch("gui_components.pipeline._run_cmd", side_effect=fake_run_cmd), \
         patch("gui_components.pipeline._find_video_srt", return_value=None):
        pipeline.run_video_pipeline(**kwargs)

    return captured["args"]


def test_run_video_pipeline_omits_ocr_flags_by_default():
    args = _run_and_capture_cmd_args()
    assert "--ocr" not in args
    assert "--ocr-region" not in args


def test_run_video_pipeline_adds_ocr_flag():
    args = _run_and_capture_cmd_args(use_ocr=True)
    assert "--ocr" in args


def test_run_video_pipeline_adds_ocr_region_flag():
    args = _run_and_capture_cmd_args(use_ocr=True, ocr_region=(0.0, 0.5, 1.0, 0.5))
    assert "--ocr-region" in args
    idx = args.index("--ocr-region")
    assert args[idx + 1] == "0.0,0.5,1.0,0.5"


def test_run_video_pipeline_omits_ocr_fps_by_default():
    args = _run_and_capture_cmd_args(use_ocr=True)
    assert "--ocr-fps" not in args


def test_run_video_pipeline_adds_ocr_fps_flag():
    args = _run_and_capture_cmd_args(use_ocr=True, ocr_fps=8)
    assert "--ocr-fps" in args
    idx = args.index("--ocr-fps")
    assert args[idx + 1] == "8"
