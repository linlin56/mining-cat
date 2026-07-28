from ocr_mining.builder import build_segments


def test_continuous_line_becomes_one_segment():
    frame_records = [(0.0, "hello"), (1.0, "hello"), (2.0, "hello")]
    segs = build_segments(frame_records)
    assert len(segs) == 1
    assert segs[0].start == 0.0
    assert segs[0].end == 3.0
    assert segs[0].text == "hello"


def test_single_blank_frame_does_not_fragment_line():
    frame_records = [(0.0, "hello"), (1.0, ""), (2.0, "hello")]
    segs = build_segments(frame_records)
    assert len(segs) == 1
    assert segs[0].start == 0.0
    assert segs[0].end == 3.0


def test_two_consecutive_blank_frames_close_the_line():
    frame_records = [(0.0, "hello"), (1.0, ""), (2.0, ""), (3.0, "hello")]
    segs = build_segments(frame_records)
    assert len(segs) == 2
    assert segs[0].start == 0.0
    assert segs[0].end == 1.0  # end is last actual detection + frame_duration, not stretched through the blanks
    assert segs[1].start == 3.0


def test_fuzzy_merge_keeps_longest_text_variant():
    frame_records = [(0.0, "Bonjour tout le mond"), (1.0, "Bonjour tout le monde")]
    segs = build_segments(frame_records)
    assert len(segs) == 1
    assert segs[0].text == "Bonjour tout le monde"


def test_dissimilar_text_starts_a_new_line():
    frame_records = [(0.0, "first line"), (1.0, "completely different text")]
    segs = build_segments(frame_records)
    assert len(segs) == 2
    assert segs[0].text == "first line"
    assert segs[1].text == "completely different text"


def test_trailing_open_line_is_flushed_at_end():
    frame_records = [(0.0, "hello"), (1.0, "hello")]
    segs = build_segments(frame_records)
    assert len(segs) == 1
    assert segs[0].end == 2.0


def test_no_frames_produces_no_segments():
    assert build_segments([]) == []


def test_all_blank_frames_produce_no_segments():
    assert build_segments([(0.0, ""), (1.0, ""), (2.0, "")]) == []


def test_custom_frame_duration_extends_segment_end():
    frame_records = [(0.0, "hello"), (0.5, "hello")]
    segs = build_segments(frame_records, frame_duration=0.5)
    assert segs[0].end == 1.0
