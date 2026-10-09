Chapters = list[tuple[str, str]]


class SelectionError(ValueError):
    pass


def select_chapters(chapters: Chapters, range_str: str | None = None, chapters_str: str | None = None) -> Chapters:
    """The chapters picked with a range ("4-9") or a list ("3,4,5"), numbered from 1. All of them by default."""
    if range_str:
        try:
            a, b = range_str.split("-")
            return chapters[int(a) - 1: int(b)]
        except (ValueError, IndexError):
            raise SelectionError(f"invalid --range: {range_str!r}  (expected format: A-B)")
    if chapters_str:
        try:
            indices = [int(x) - 1 for x in chapters_str.split(",")]
        except ValueError:
            raise SelectionError(f"invalid --chapters: {chapters_str!r}")
        return [chapters[i] for i in indices if 0 <= i < len(chapters)]
    return chapters
