"""How close two OCR readings are: the same subtitle line read with a mistake or two is the same line."""
import difflib

TEXT_SIMILARITY_THRESHOLD = 0.85


def text_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# Minimum single-character insertions/deletions/substitutions to turn `a` into `b`.
# Used instead of text_similarity's ratio for near-duplicate detection
# a ratio threshold scales with string length, whereas "off by ~1 character" should mean the same thing regardless of line length.
def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr_row = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr_row[j] = min(
                prev_row[j] + 1,       # deletion
                curr_row[j - 1] + 1,   # insertion
                prev_row[j - 1] + cost,  # substitution
            )
        prev_row = curr_row
    return prev_row[-1]


def is_near_duplicate(a: str, b: str, max_edits: int = 1) -> bool:
    return levenshtein_distance(a, b) <= max_edits


