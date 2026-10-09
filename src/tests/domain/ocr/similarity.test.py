from PIL import Image

from miningcat.domain.languages import Language
from miningcat.domain.ocr import frame_similarity, plausibility, text_similarity


# text_similarity
def test_text_similarity_identical_strings():
    assert text_similarity.text_similarity("hello world", "hello world") == 1.0


def test_text_similarity_completely_different_strings():
    assert text_similarity.text_similarity("hello world", "xyz") < text_similarity.TEXT_SIMILARITY_THRESHOLD


def test_text_similarity_minor_variation_above_threshold():
    # A single-character OCR misread should still be considered "the same line".
    assert text_similarity.text_similarity("Bonjour tout le monde", "Bonjour tout le mondc") >= text_similarity.TEXT_SIMILARITY_THRESHOLD


# frames_are_similar
def test_frames_are_similar_identical_images():
    a = Image.new("RGB", (64, 64), color=(10, 20, 30))
    b = a.copy()
    assert frame_similarity.frames_are_similar(a, b) is True


def test_frames_are_similar_different_solid_colors():
    a = Image.new("RGB", (64, 64), color=(0, 0, 0))
    b = Image.new("RGB", (64, 64), color=(255, 255, 255))
    assert frame_similarity.frames_are_similar(a, b) is False


def test_frames_are_similar_slightly_perturbed_image():
    a = Image.new("RGB", (64, 64), color=(100, 100, 100))
    b = Image.new("RGB", (64, 64), color=(102, 100, 100))  # tiny compression-noise-like delta
    assert frame_similarity.frames_are_similar(a, b) is True


# A subtitle line appearing on a plain background (black bars, a game's dialog box): a small share of
# the pixels, so a small mean difference, but those pixels change completely.
def test_frames_differ_when_a_line_appears_on_a_plain_background():
    blank = Image.new("RGB", (1280, 240), color=(20, 20, 20))
    subtitle = blank.copy()
    subtitle.paste((255, 255, 255), (440, 100, 840, 112))
    assert frame_similarity.frames_are_similar(subtitle, blank) is False
    assert frame_similarity.frames_are_similar(subtitle, subtitle.copy()) is True


# _downscale_for_diff - a subtitle crop is wide and short; squashing it into a
# fixed small square destroys the character-stroke detail needed to tell two
# different lines of text apart (see dedup.py's docstring for the incident).
def test_downscale_for_diff_preserves_aspect_ratio_of_wide_crop():
    wide_image = Image.new("RGB", (1280, 240), color=(0, 0, 0))
    result = frame_similarity._downscale_for_diff(wide_image)
    assert result.size == (256, 48)


def test_downscale_for_diff_does_not_upscale_small_images():
    small_image = Image.new("RGB", (100, 20), color=(0, 0, 0))
    result = frame_similarity._downscale_for_diff(small_image)
    assert result.size == (100, 20)


# is_plausible_text
def test_is_plausible_text_accepts_cjk_for_mandarin():
    assert plausibility.is_plausible_text("這是一句話", Language.MANDARIN_TW) is True


def test_is_plausible_text_rejects_garbage_for_cjk_language():
    assert plausibility.is_plausible_text("IY", Language.MANDARIN_TW) is False
    assert plausibility.is_plausible_text("000", Language.JAPANESE) is False
    assert plausibility.is_plausible_text("", Language.MANDARIN_CN) is False


def test_is_plausible_text_accepts_latin_letters_for_french():
    assert plausibility.is_plausible_text("Bonjour", Language.FRENCH) is True


def test_is_plausible_text_rejects_cjk_for_latin_language():
    assert plausibility.is_plausible_text("這是一句話", Language.FRENCH) is False


def test_is_plausible_text_rejects_symbols_only_for_latin_language():
    assert plausibility.is_plausible_text("000", Language.ENGLISH_US) is False
    assert plausibility.is_plausible_text("）", Language.ENGLISH_US) is False


# levenshtein_distance
def test_levenshtein_distance_identical_strings():
    assert text_similarity.levenshtein_distance("hello", "hello") == 0


def test_levenshtein_distance_single_substitution():
    # real-world case: 白 misread as 口 by OCR.
    assert text_similarity.levenshtein_distance("我可以明白", "我可以明口") == 1


def test_levenshtein_distance_single_insertion_and_deletion():
    assert text_similarity.levenshtein_distance("hello", "helloo") == 1
    assert text_similarity.levenshtein_distance("helloo", "hello") == 1


def test_levenshtein_distance_empty_strings():
    assert text_similarity.levenshtein_distance("", "") == 0
    assert text_similarity.levenshtein_distance("", "abc") == 3
    assert text_similarity.levenshtein_distance("abc", "") == 3


def test_levenshtein_distance_completely_different_strings():
    assert text_similarity.levenshtein_distance("hello", "xyz") >= 4


# is_near_duplicate
def test_is_near_duplicate_true_within_default_max_edits():
    assert text_similarity.is_near_duplicate("我可以明白", "我可以明口") is True


def test_is_near_duplicate_false_beyond_max_edits():
    assert text_similarity.is_near_duplicate("hello world", "xyz") is False


def test_is_near_duplicate_respects_custom_max_edits():
    assert text_similarity.is_near_duplicate("hello", "help") is False  # 2 edits
    assert text_similarity.is_near_duplicate("hello", "help", max_edits=2) is True
