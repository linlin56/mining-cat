from align import Segment
from ocr_mining.builder import _consensus_text, _lines_are_near_duplicate, build_segments, merge_near_duplicates


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


# merge_near_duplicates
def test_merge_near_duplicates_reproduces_reported_bug():
    # Real case from my own tests: 我可以明白 -> 我可以明口 (白 misread as 口),
    # split into two touching (zero-gap) segments by build_segments.
    segs = [
        Segment(1, 18 * 60 + 5, 18 * 60 + 6, "我可以明白"),
        Segment(2, 18 * 60 + 6, 18 * 60 + 6.5, "我可以明口"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].text == "我可以明白"  # keeps the first (earlier) reading
    assert merged[0].start == 18 * 60 + 5
    assert merged[0].end == 18 * 60 + 6.5


def test_merge_near_duplicates_chains_three_in_a_row():
    segs = [
        Segment(1, 0.0, 1.0, "hello world"),
        Segment(2, 1.0, 2.0, "hallo world"),
        Segment(3, 2.0, 3.0, "hellp world"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].text == "hello world"
    assert merged[0].end == 3.0


def test_merge_near_duplicates_leaves_dissimilar_segments_alone():
    segs = [
        Segment(1, 0.0, 1.0, "first line"),
        Segment(2, 1.0, 2.0, "completely different text"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 2


def test_merge_near_duplicates_does_not_merge_across_a_real_gap():
    # Same text, but separated by a real gap (e.g. the line genuinely
    # disappeared and reappeared) - should NOT be merged.
    segs = [
        Segment(1, 0.0, 1.0, "hello"),
        Segment(2, 3.0, 4.0, "hello"),
    ]
    merged = merge_near_duplicates(segs, max_gap=0.0)
    assert len(merged) == 2


def test_merge_near_duplicates_respects_max_gap_tolerance():
    segs = [
        Segment(1, 0.0, 1.0, "hello"),
        Segment(2, 1.4, 2.0, "hallo"),
    ]
    assert len(merge_near_duplicates(segs, max_gap=0.5)) == 1
    assert len(merge_near_duplicates(segs, max_gap=0.1)) == 2


def test_merge_near_duplicates_empty_list():
    assert merge_near_duplicates([]) == []


def test_merge_near_duplicates_single_segment():
    segs = [Segment(1, 0.0, 1.0, "hello")]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].text == "hello"


# _consensus_text
def test_consensus_text_single_reading_returned_as_is():
    assert _consensus_text(["hello"]) == "hello"


def test_consensus_text_picks_majority_character_per_position():
    # Scattered errors at different positions -> the correct char wins at each.
    assert _consensus_text(["hello", "hallo", "hellp", "hxllo"]) == "hello"


def test_consensus_text_breaks_ties_toward_first_reading():
    assert _consensus_text(["我可以明白", "我可以明口"]) == "我可以明白"


def test_consensus_text_ignores_minority_length_outliers():
    # "hell" (missing a char) is a length outlier and shouldn't affect voting.
    assert _consensus_text(["hello", "hello", "hallo", "hell"]) == "hello"


# merge_near_duplicates - clustering + consensus voting on longer noisy runs
def test_merge_near_duplicates_recovers_correct_text_from_scattered_noise():
    # Simulates a higher-fps run: many reads of the same line with issues on OCR
    texts = [
        "電腦終端機沒有人的時候",
        "電脶終端機沒有人的時候",
        "電腦終端横沒有人的時候",
        "铝腦終端機沒有人的時候",
        "電腦終端機沒有人的哮候",
        "電腦終端機没有人的時候",
        "電腦終端機沒有人的時候",
    ]
    segs = [Segment(i, i * 0.125, (i + 1) * 0.125, t) for i, t in enumerate(texts)]
    merged = merge_near_duplicates(segs, max_gap=0.125)
    assert len(merged) == 1
    assert merged[0].text == "電腦終端機沒有人的時候"
    assert merged[0].start == 0.0
    assert merged[0].end == len(texts) * 0.125


def test_merge_near_duplicates_cluster_scales_tolerance_with_length():
    # "hello world" vs "hallo wxrld" differ by 2 characters
    # more than the base max_edits=1
    # but within the scaled cluster tolerance for an 11-character line.
    # so this uses the regular ratio, not the higher contiguous one.
    segs = [
        Segment(1, 0.0, 0.5, "hello world"),
        Segment(2, 0.7, 1.0, "hallo wxrld"),
    ]
    merged = merge_near_duplicates(segs, max_gap=0.2)
    assert len(merged) == 1


def test_merge_near_duplicates_contiguous_pair_gets_higher_tolerance():
    # Real case from my tests
    # these two touch exactly (one ends where the next starts) and differ by 4 of 11 characters (~36%)
    # too much for the regular 30% cluster ratio, but within the contiguous 50% one.
    segs = [
        Segment(1, 0.0, 1.0, "芚腦纲上到底有沒有花8"),
        Segment(2, 1.0, 1.5, "電腦網上到成有沒有花？"),
    ]
    merged = merge_near_duplicates(segs, max_gap=0.125)
    assert len(merged) == 1


def test_merge_near_duplicates_same_diff_with_a_gap_is_not_merged():
    # Same ~36% character difference as the contiguous case above, but with a small nonzero gap
    # stays under the regular (stricter) ratio, so it's NOT merged, since a gap is weaker evidence the line didn't actually change.
    segs = [
        Segment(1, 0.0, 1.0, "芚腦纲上到底有沒有花8"),
        Segment(2, 1.1, 1.5, "電腦網上到成有沒有花？"),
    ]
    merged = merge_near_duplicates(segs, max_gap=0.125)
    assert len(merged) == 2


def test_merge_near_duplicates_contiguous_recovers_despite_dissimilar_middle():
    # first and third readings are identical, but the middle one differs enough (from the anchor) that a naive pairwise-only comparison could fragment this into two groups
    # the contiguous tolerance keeps all three in one cluster, and voting recovers the 2-out-of-3 majority reading.
    segs = [
        Segment(1, 0.0, 1.375, "例是有一些關於查的傳用"),
        Segment(2, 1.375, 3.375, "倒是有一些關於官的傅聞"),
        Segment(3, 3.375, 4.125, "例是有一些關於查的傳用"),
    ]
    merged = merge_near_duplicates(segs, max_gap=0.125)
    assert len(merged) == 1
    assert merged[0].text == "例是有一些關於查的傳用"


def test_merge_near_duplicates_default_max_gap_bridges_a_brief_ocr_dropout():
    # a 0.5s gap (an OCR dropout longer than a single frame, not a real line change) between two 1-character-apart readings of the same line.
    # The default max_gap (1 second) now bridges this without needing an explicit override.
    segs = [
        Segment(51, 6 * 60 + 6.000, 6 * 60 + 6.250, "其實我在前些哮候"),
        Segment(52, 6 * 60 + 6.750, 6 * 60 + 7.500, "其實我在前些時候"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].start == 6 * 60 + 6.000
    assert merged[0].end == 6 * 60 + 7.500


def test_merge_near_duplicates_default_max_gap_is_one_second():
    from ocr_mining.builder import DEFAULT_MAX_MERGE_GAP
    assert DEFAULT_MAX_MERGE_GAP == 1.0


# _lines_are_near_duplicate - multi-line ("\n") aware comparison
def test_lines_are_near_duplicate_reduces_to_single_line_comparison():
    assert _lines_are_near_duplicate("hello", "hallo", max_edits=1, is_contiguous=False) is True
    assert _lines_are_near_duplicate("hello", "xyz", max_edits=1, is_contiguous=False) is False


def test_lines_are_near_duplicate_tolerates_a_missing_line():
    # Real case from Layer8_ocr.srt: second line dropped out entirely for a frame.
    anchor = "會對電膦綱絡造成\n非带大的报街"
    candidate = "會對電膦綱絡造成"  # second line missing this frame
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is True


def test_lines_are_near_duplicate_tolerates_the_other_line_missing():
    # Same as above but the FIRST line is the one missing this time.
    anchor = "會對電膦綱絡造成\n非带大的报街"
    candidate = "非常大的报街"  # first line missing, second line present (noisy)
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is True


def test_lines_are_near_duplicate_false_when_no_line_matches():
    anchor = "會對電膦綱絡造成\n非带大的报街"
    candidate = "completely unrelated content here"
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is False


def test_lines_are_near_duplicate_tolerates_swapped_line_order():
    assert _lines_are_near_duplicate("不會的\n不是", "不是\n不會的", max_edits=1, is_contiguous=True) is True


# merge_near_duplicates - multi-line clustering + reconstruction
def test_merge_near_duplicates_recovers_multiline_subtitle_with_dropped_lines():
    # a two-line subtitle where one line or the other drops out for some frames 
    # previously stayed fragmented into 5 separate entries since the whole blob was compared as one string.
    segs = [
        Segment(74, 9 * 60 + 38.250, 9 * 60 + 39.000, "會對電膦綱絡造成\n非带大的报街"),
        Segment(75, 9 * 60 + 39.000, 9 * 60 + 39.125, "會對芚膦綱絳造成"),
        Segment(76, 9 * 60 + 39.125, 9 * 60 + 41.375, "會對電膦綱絡造成\n非常大的損等"),
        Segment(77, 9 * 60 + 41.375, 9 * 60 + 41.500, "非常大的报街"),
        Segment(78, 9 * 60 + 41.500, 9 * 60 + 42.750, "會對電膦綱絡造成\n非常大的損安"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].start == 9 * 60 + 38.250
    assert merged[0].end == 9 * 60 + 42.750
    lines = merged[0].text.split("\n")
    assert len(lines) == 2
    assert lines[0] == "會對電膦綱絡造成"


def test_consensus_text_multiline_votes_per_line_independently():
    texts = [
        "line one\nline two",
        "line onx\nline two",
        "line one\nlino two",
    ]
    assert _consensus_text(texts) == "line one\nline two"


# _lines_are_near_duplicate joined-lines fallback (OCR sometimes reads a multi-line subtitle's lines run together as one, with no line break)
def test_lines_are_near_duplicate_matches_joined_lines_same_order():
    anchor = "line one\nline two"
    candidate = "line oneline two"  # both lines read together, no break
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is True


def test_lines_are_near_duplicate_matches_joined_lines_reversed_order():
    # the two lines get read in reverse order and joined together as a single line in the same frame.
    anchor = "直在然視我\n思不到你"
    candidate = "思不到你一直在然視我"  # reversed order, joined, +1 stray character
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is True


def test_lines_are_near_duplicate_rejects_unrelated_single_line():
    anchor = "line one\nline two"
    candidate = "completely unrelated content here"
    assert _lines_are_near_duplicate(anchor, candidate, max_edits=1, is_contiguous=True) is False


def test_merge_near_duplicates_recovers_multiline_subtitle_with_joined_and_reordered_reading():
    # a two-line subtitle where the middle reading joins both lines together (reversed) with no line break
    # previously stayed fragmented into 3 separate entries.
    segs = [
        Segment(136, 15 * 60 + 43.125, 15 * 60 + 44.250, "直在然視我\n思不到你"),
        Segment(137, 15 * 60 + 44.250, 15 * 60 + 44.500, "思不到你一直在然視我"),
        Segment(138, 15 * 60 + 44.500, 15 * 60 + 45.625, "思不到你\n宜在盈視我"),
    ]
    merged = merge_near_duplicates(segs)
    assert len(merged) == 1
    assert merged[0].start == 15 * 60 + 43.125
    assert merged[0].end == 15 * 60 + 45.625
