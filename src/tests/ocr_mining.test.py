from unittest.mock import MagicMock, patch

from language import Language
from ocr_mining import pipeline


def test_generate_segments_orchestrates_extraction_ocr_and_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DIR_OCR_FRAMES", tmp_path / "ocr_frames")

    video_file = tmp_path / "movie.mp4"
    frame_paths = [tmp_path / f"frame_{i:06d}.jpg" for i in range(3)]
    for path in frame_paths:
        path.write_bytes(b"fake-jpeg")

    mock_probe_dimensions = MagicMock(return_value=(1920, 1080))
    mock_region_to_pixels = MagicMock(return_value=(0, 720, 1920, 360))
    mock_extract_cropped_frames = MagicMock(return_value=frame_paths)

    # Frame 1 is flagged as similar to frame 0 -> OCR should be skipped for it,
    # reusing frame 0's recognized text instead.
    mock_frames_are_similar = MagicMock(side_effect=[True, False])

    mock_engine = MagicMock()
    mock_engine.read_text.side_effect = ["hello", "world"]
    mock_engine_cls = MagicMock(return_value=mock_engine)

    mock_build_segments = MagicMock(return_value=["fake segment"])

    with patch("ocr_mining.frames.probe_dimensions", mock_probe_dimensions), \
         patch("ocr_mining.frames.region_to_pixels", mock_region_to_pixels), \
         patch("ocr_mining.frames.extract_cropped_frames", mock_extract_cropped_frames), \
         patch("ocr_mining.dedup.frames_are_similar", mock_frames_are_similar), \
         patch("ocr_mining.pipeline.Image.open", return_value=MagicMock()), \
         patch("ocr_mining.pipeline.OcrEngine", mock_engine_cls), \
         patch("ocr_mining.builder.build_segments", mock_build_segments):
        result = pipeline.generate_segments(video_file, language=Language.FRENCH, fps=1)

    mock_extract_cropped_frames.assert_called_once()
    mock_engine_cls.assert_called_once_with(Language.FRENCH)
    # Only 2 OCR calls: frame 1 reused frame 0's result instead of running OCR again.
    assert mock_engine.read_text.call_count == 2
    frame_records = mock_build_segments.call_args.args[0]
    assert frame_records == [(0.0, "hello"), (1.0, "hello"), (2.0, "world")]
    assert result == ["fake segment"]
    assert not (tmp_path / "ocr_frames" / "movie").exists()


def test_generate_segments_filters_implausible_text_for_language(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DIR_OCR_FRAMES", tmp_path / "ocr_frames")

    video_file = tmp_path / "movie.mp4"
    frame_paths = [tmp_path / f"frame_{i:06d}.jpg" for i in range(2)]
    for path in frame_paths:
        path.write_bytes(b"fake-jpeg")

    mock_engine = MagicMock()
    # First frame: real French dialogue. Second: OCR garbage with no Latin letters.
    mock_engine.read_text.side_effect = ["Bonjour", "000"]

    with patch("ocr_mining.frames.probe_dimensions", return_value=(1920, 1080)), \
         patch("ocr_mining.frames.region_to_pixels", return_value=(0, 720, 1920, 360)), \
         patch("ocr_mining.frames.extract_cropped_frames", return_value=frame_paths), \
         patch("ocr_mining.dedup.frames_are_similar", return_value=False), \
         patch("ocr_mining.pipeline.Image.open", return_value=MagicMock()), \
         patch("ocr_mining.pipeline.OcrEngine", return_value=mock_engine), \
         patch("ocr_mining.builder.build_segments", return_value=[]) as mock_build_segments:
        pipeline.generate_segments(video_file, language=Language.FRENCH, fps=1)

    frame_records = mock_build_segments.call_args.args[0]
    assert frame_records == [(0.0, "Bonjour"), (1.0, "")]


def test_generate_segments_uses_default_region_when_none_given(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DIR_OCR_FRAMES", tmp_path / "ocr_frames")
    video_file = tmp_path / "movie.mp4"

    mock_region_to_pixels = MagicMock(return_value=(0, 0, 100, 100))

    with patch("ocr_mining.frames.probe_dimensions", return_value=(100, 100)), \
         patch("ocr_mining.frames.region_to_pixels", mock_region_to_pixels), \
         patch("ocr_mining.frames.extract_cropped_frames", return_value=[]), \
         patch("ocr_mining.pipeline.OcrEngine"), \
         patch("ocr_mining.builder.build_segments", return_value=[]):
        pipeline.generate_segments(video_file, language=Language.FRENCH, region=None)

    mock_region_to_pixels.assert_called_once_with(pipeline.frames.DEFAULT_REGION, 100, 100)


def test_generate_segments_cleans_up_frames_dir_even_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DIR_OCR_FRAMES", tmp_path / "ocr_frames")
    video_file = tmp_path / "movie.mp4"
    frames_dir = tmp_path / "ocr_frames" / "movie"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_000000.jpg").touch()

    with patch("ocr_mining.frames.probe_dimensions", return_value=(100, 100)), \
         patch("ocr_mining.frames.region_to_pixels", return_value=(0, 0, 100, 100)), \
         patch("ocr_mining.frames.extract_cropped_frames", return_value=[frames_dir / "frame_000000.jpg"]), \
         patch("ocr_mining.pipeline.OcrEngine", side_effect=RuntimeError("boom")):
        try:
            pipeline.generate_segments(video_file, language=Language.FRENCH)
        except RuntimeError:
            pass

    assert not frames_dir.exists()
