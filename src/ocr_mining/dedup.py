import difflib
import re

from PIL import Image, ImageChops, ImageStat

from language import Language

TEXT_SIMILARITY_THRESHOLD = 0.85
MAX_PIXEL_DIFF_RATIO = 0.02

# Preserve aspect ratio and use a larger downscale size 
# so subtitle text remains distinguishable and real changes do not get mistaken for identical frames.
_DIFF_MAX_DIM = 256


def _downscale_for_diff(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = _DIFF_MAX_DIM / max(width, height)
    if scale < 1:
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))
    return image.convert("L")


# Compares two frames cheaply: downscales both to a grayscale thumbnail (preserving aspect ratio)
# measures the mean per-pixel difference
# Uses a similarity threshold rather than an exact/hash match, since lossy video compression means visually-identical frames aren't byte-identical.
def frames_are_similar(a: Image.Image, b: Image.Image, threshold: float = MAX_PIXEL_DIFF_RATIO) -> bool:
    a_small = _downscale_for_diff(a)
    b_small = _downscale_for_diff(b)
    diff = ImageChops.difference(a_small, b_small)
    mean_diff = ImageStat.Stat(diff).mean[0]
    return (mean_diff / 255) <= threshold


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


_CJK_LANGUAGES = frozenset({Language.MANDARIN_TW, Language.MANDARIN_CN, Language.JAPANESE})
# CJK ideographs + hiragana/katakana (incl. halfwidth katakana).
_CJK_PATTERN = re.compile(r"[一-鿿぀-ヿｦ-ﾟ]")
_LATIN_LETTER_PATTERN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


# Frames with no real subtitle sometimes still OCR
# Rejecting text that doesn't contain at least one character from the target language's script is a cheap filter since the language is already known ahead of time.
def is_plausible_text(text: str, language: Language) -> bool:
    if not text:
        return False
    pattern = _CJK_PATTERN if language in _CJK_LANGUAGES else _LATIN_LETTER_PATTERN
    return bool(pattern.search(text))
