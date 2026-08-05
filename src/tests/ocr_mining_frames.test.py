from unittest.mock import MagicMock, patch

from ocr_mining import frames


# OCR_FPS constants
def test_ocr_fps_default_within_range():
    assert frames.OCR_FPS_MIN == 2
    assert frames.OCR_FPS_MAX == 12
    assert frames.OCR_FPS_MIN <= frames.OCR_FPS_DEFAULT <= frames.OCR_FPS_MAX


def test_extract_cropped_frames_defaults_to_ocr_fps_default():
    import inspect
    assert inspect.signature(frames.extract_cropped_frames).parameters["fps"].default == frames.OCR_FPS_DEFAULT


# region_to_pixels
def test_region_to_pixels_bottom_third():
    assert frames.region_to_pixels(frames.DEFAULT_REGION, 1920, 1080) == (0, 720, 1920, 360)


def test_region_to_pixels_clamps_to_frame_edges():
    # A region that would overflow past the right/bottom edge due to rounding is clamped.
    assert frames.region_to_pixels((0.5, 0.5, 0.6, 0.6), 100, 100) == (50, 50, 50, 50)


def test_region_to_pixels_full_frame():
    assert frames.region_to_pixels((0.0, 0.0, 1.0, 1.0), 640, 480) == (0, 0, 640, 480)


# probe_dimensions / probe_duration
def test_probe_dimensions_reads_first_video_stream():
    probe_result = {
        "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1280, "height": 720},
        ]
    }
    with patch("ocr_mining.frames.ffmpeg.probe", return_value=probe_result):
        assert frames.probe_dimensions("movie.mp4") == (1280, 720)


def test_probe_duration_reads_format_duration():
    probe_result = {"format": {"duration": "12.5"}}
    with patch("ocr_mining.frames.ffmpeg.probe", return_value=probe_result):
        assert frames.probe_duration("movie.mp4") == 12.5


# grab_sample_frame
def test_grab_sample_frame_uses_fraction_of_duration(tmp_path):
    video_file = tmp_path / "movie.mp4"
    output_path = tmp_path / "preview.jpg"

    mock_stream = MagicMock()
    mock_stream.output.return_value = mock_stream
    mock_stream.overwrite_output.return_value = mock_stream

    with patch("ocr_mining.frames.probe_duration", return_value=100.0), \
         patch("ocr_mining.frames.ffmpeg.input", return_value=mock_stream) as mock_input:
        result = frames.grab_sample_frame(video_file, output_path, at_fraction=0.25)

    mock_input.assert_called_once_with(str(video_file), ss=25.0)
    mock_stream.run.assert_called_once()
    assert result == output_path


# grab_sample_frames
def test_grab_sample_frames_grabs_one_per_fraction(tmp_path):
    video_file = tmp_path / "movie.mp4"
    output_dir = tmp_path / "preview"

    with patch("ocr_mining.frames.grab_sample_frame") as mock_grab:
        mock_grab.side_effect = lambda video_file, output_path, at_fraction: output_path
        result = frames.grab_sample_frames(video_file, output_dir, fractions=(0.1, 0.5, 0.9))

    assert mock_grab.call_count == 3
    fractions_used = [call.kwargs["at_fraction"] for call in mock_grab.call_args_list]
    assert fractions_used == [0.1, 0.5, 0.9]
    assert result == [
        output_dir / "preview_00.jpg",
        output_dir / "preview_01.jpg",
        output_dir / "preview_02.jpg",
    ]


def test_grab_sample_frames_default_fractions_avoid_start_and_end():
    assert frames.DEFAULT_PREVIEW_FRACTIONS[0] > 0.0
    assert frames.DEFAULT_PREVIEW_FRACTIONS[-1] < 1.0
    assert len(frames.DEFAULT_PREVIEW_FRACTIONS) == 10


# extract_cropped_frames
def test_extract_cropped_frames_builds_fps_and_crop_filters(tmp_path):
    video_file = tmp_path / "movie.mp4"
    output_dir = tmp_path / "frames"

    mock_stream = MagicMock()
    mock_stream.filter.return_value = mock_stream
    mock_stream.output.return_value = mock_stream
    mock_stream.overwrite_output.return_value = mock_stream

    with patch("ocr_mining.frames.ffmpeg.input", return_value=mock_stream) as mock_input:
        (output_dir / "frame_000000.jpg").parent.mkdir(parents=True)
        (output_dir / "frame_000000.jpg").touch()
        (output_dir / "frame_000001.jpg").touch()
        result = frames.extract_cropped_frames(video_file, output_dir, (0, 720, 1920, 360), fps=1)

    mock_input.assert_called_once_with(str(video_file))
    mock_stream.filter.assert_any_call("fps", fps=1)
    mock_stream.filter.assert_any_call("crop", 1920, 360, 0, 720)
    mock_stream.run.assert_called_once()
    assert result == [output_dir / "frame_000000.jpg", output_dir / "frame_000001.jpg"]
