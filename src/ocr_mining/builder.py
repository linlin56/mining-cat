from align import Segment
from ocr_mining.dedup import TEXT_SIMILARITY_THRESHOLD, text_similarity

EMPTY_FRAME_TOLERANCE = 2  # consecutive blank frames required before closing a line


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
