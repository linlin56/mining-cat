from collections import Counter

from align import Segment
from ocr_mining.dedup import TEXT_SIMILARITY_THRESHOLD, is_near_duplicate, text_similarity
# This constants are for OCR subtitles cleanup
 # consecutive blank frames required before closing a line
EMPTY_FRAME_TOLERANCE = 2 

# baseline max character edits for two adjacent segments to be considered the same line
# This is because OCR can make mistakes, especially with poor quality frames, and we want to merge segments that are likely the same subtitle line even if they have minor differences in the detected text.
NEAR_DUPLICATE_MAX_EDITS = 1  

# ratio of the anchor text length to the maximum allowed edits for two segments to be considered near-duplicates
CLUSTER_EDIT_RATIO = 0.3

# Two segments with zero gap between them (one ends exactly when the next starts) are almost always the same subtitle line caught mid-transition
# a real line change is rare to land with no blank frame at all in between.
CLUSTER_EDIT_RATIO_CONTIGUOUS = 0.5
# The epsilon value for determining if two segments are contiguous (i.e., have no gap between them). This accounts for floating-point inaccuracies in timestamp calculations.
_CONTIGUOUS_EPSILON = 1e-6

# A brief OCR dropout (a few frames where the line failed to read at all) can leave a real gap between two segments that are still the same line
# a full second is generous enough to bridge that without risk merging genuine cases.
DEFAULT_MAX_MERGE_GAP = 1.0


# frame_records: list of (timestamp, text) pairs in increasing timestamp order,
# one per sampled frame - text is "" (or blank) when no subtitle was detected.
def build_segments(frame_records: list[tuple[float, str]], frame_duration: float = 1.0) -> list[Segment]:
    segments: list[Segment] = []
    active_start: float | None = None
    active_text = ""
    active_last_seen = 0.0
    empty_count = 0

    def close_active() -> None:
        segments.append(Segment(0, active_start, active_last_seen + frame_duration, active_text))

    for timestamp, raw_text in frame_records:
        text = (raw_text or "").strip()

        if not text:
            if active_start is not None:
                empty_count += 1
                if empty_count >= EMPTY_FRAME_TOLERANCE:
                    close_active()
                    active_start = None
                    active_text = ""
                    empty_count = 0
            continue

        if active_start is None:
            active_start = timestamp
            active_text = text
            active_last_seen = timestamp
            empty_count = 0
        elif text_similarity(active_text, text) >= TEXT_SIMILARITY_THRESHOLD:
            active_last_seen = timestamp
            if len(text) > len(active_text):
                active_text = text
            empty_count = 0
        else:
            close_active()
            active_start = timestamp
            active_text = text
            active_last_seen = timestamp
            empty_count = 0

    if active_start is not None:
        close_active()

    return segments


def _cluster_max_edits(anchor_text: str, max_edits: int, is_contiguous: bool) -> int:
    ratio = CLUSTER_EDIT_RATIO_CONTIGUOUS if is_contiguous else CLUSTER_EDIT_RATIO
    return max(max_edits, round(len(anchor_text) * ratio))


# A multi-line subtitle (embedded "\n") sometimes has one of its lines drop out entirely for a frame while the other stays stable
# comparing the whole blob as one string then treats that as a huge difference and blocks the merge.
# Only requiring each line of the SHORTER reading to match some line of the longer one tolerates a missing line without having to guess which position it dropped from
# it also incidentally tolerates the rarer case of two lines swapping order.
# Reduces to a plain single-line comparison when neither text has a "\n".
def _lines_are_near_duplicate(anchor_text: str, candidate_text: str, max_edits: int, is_contiguous: bool) -> bool:
    anchor_lines = anchor_text.split("\n")
    candidate_lines = candidate_text.split("\n")
    shorter, longer = (
        (anchor_lines, candidate_lines) if len(anchor_lines) <= len(candidate_lines)
        else (candidate_lines, anchor_lines)
    )
    if all(
        any(is_near_duplicate(line, other, _cluster_max_edits(line, max_edits, is_contiguous)) for other in longer)
        for line in shorter
    ):
        return True
    # The OCR sometimes reads a multi-line subtitle's lines run together as a single line instead (no line break detected that frame)
    #  if the other reading is just one line, also check it against the longer reading's lines joined together with no separator, trying both the given order and reversed (lines can swap which one gets read first).
    if len(shorter) == 1:
        joined = "".join(longer)
        allowed = _cluster_max_edits(joined, max_edits, is_contiguous)
        if is_near_duplicate(joined, shorter[0], allowed):
            return True
        joined_reversed = "".join(reversed(longer))
        if is_near_duplicate(joined_reversed, shorter[0], allowed):
            return True
    return False


# Reconstructs a single "best guess" line from a set of OCR readings of what is presumed to be the same line
# by voting on the most frequent character at each position.
# OCR misreads are scattered essentially at random across positions, so the correct character is almost always the majority at its position even when no single reading is fully correct.
# Falls back to the first reading's character on ties
def _consensus_line(texts: list[str]) -> str:
    if len(texts) == 1:
        return texts[0]
    common_length, _ = Counter(len(t) for t in texts).most_common(1)[0]
    candidates = [t for t in texts if len(t) == common_length]
    return "".join(
        Counter(t[i] for t in candidates).most_common(1)[0][0]
        for i in range(common_length)
    )


# Same idea as _consensus_line, but for a cluster of (possibly multi-line) readings
def _consensus_text(texts: list[str]) -> str:
    if len(texts) == 1:
        return texts[0]
    lines_per_text = [t.split("\n") for t in texts]
    common_line_count, _ = Counter(len(lines) for lines in lines_per_text).most_common(1)[0]
    candidates = [lines for lines in lines_per_text if len(lines) == common_line_count]
    return "\n".join(
        _consensus_line([lines[i] for lines in candidates])
        for i in range(common_line_count)
    )


# Post-processing pass over already-built segments to merge any that are likely the same sub split due to OCR issues.
def merge_near_duplicates(
    segments: list[Segment], max_edits: int = NEAR_DUPLICATE_MAX_EDITS, max_gap: float = DEFAULT_MAX_MERGE_GAP,
) -> list[Segment]:
    if not segments:
        return []

    clusters: list[list[Segment]] = [[segments[0]]]
    for seg in segments[1:]:
        cluster = clusters[-1]
        anchor = cluster[0]
        gap = seg.start - cluster[-1].end
        is_contiguous = gap <= _CONTIGUOUS_EPSILON
        if gap <= max_gap and _lines_are_near_duplicate(anchor.text, seg.text, max_edits, is_contiguous):
            cluster.append(seg)
        else:
            clusters.append([seg])

    merged = []
    for cluster in clusters:
        if len(cluster) == 1:
            merged.append(cluster[0])
        else:
            text = _consensus_text([seg.text for seg in cluster])
            merged.append(Segment(cluster[0].index, cluster[0].start, cluster[-1].end, text))
    return merged
