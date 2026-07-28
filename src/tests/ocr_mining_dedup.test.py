from PIL import Image

from language import Language
from ocr_mining import dedup


# text_similarity
def test_text_similarity_identical_strings():
    assert dedup.text_similarity("hello world", "hello world") == 1.0


def test_text_similarity_completely_different_strings():
    assert dedup.text_similarity("hello world", "xyz") < dedup.TEXT_SIMILARITY_THRESHOLD


def test_text_similarity_minor_variation_above_threshold():
    # A single-character OCR misread should still be considered "the same line".
    assert dedup.text_similarity("Bonjour tout le monde", "Bonjour tout le mondc") >= dedup.TEXT_SIMILARITY_THRESHOLD


# frames_are_similar
def test_frames_are_similar_identical_images():
    a = Image.new("RGB", (64, 64), color=(10, 20, 30))
    b = a.copy()
    assert dedup.frames_are_similar(a, b) is True


def test_frames_are_similar_different_solid_colors():
    a = Image.new("RGB", (64, 64), color=(0, 0, 0))
    b = Image.new("RGB", (64, 64), color=(255, 255, 255))
    assert dedup.frames_are_similar(a, b) is False


def test_frames_are_similar_slightly_perturbed_image():
    a = Image.new("RGB", (64, 64), color=(100, 100, 100))
    b = Image.new("RGB", (64, 64), color=(102, 100, 100))  # tiny compression-noise-like delta
    assert dedup.frames_are_similar(a, b) is True


# _downscale_for_diff - a subtitle crop is wide and short; squashing it into a
# fixed small square destroys the character-stroke detail needed to tell two
# different lines of text apart (see dedup.py's docstring for the incident).
def test_downscale_for_diff_preserves_aspect_ratio_of_wide_crop():
    wide_image = Image.new("RGB", (1280, 240), color=(0, 0, 0))
    result = dedup._downscale_for_diff(wide_image)
    assert result.size == (256, 48)


def test_downscale_for_diff_does_not_upscale_small_images():
    small_image = Image.new("RGB", (100, 20), color=(0, 0, 0))
    result = dedup._downscale_for_diff(small_image)
    assert result.size == (100, 20)


# is_plausible_text
def test_is_plausible_text_accepts_cjk_for_mandarin():
    assert dedup.is_plausible_text("這是一句話", Language.MANDARIN_TW) is True


def test_is_plausible_text_rejects_garbage_for_cjk_language():
    assert dedup.is_plausible_text("IY", Language.MANDARIN_TW) is False
    assert dedup.is_plausible_text("000", Language.JAPANESE) is False
    assert dedup.is_plausible_text("", Language.MANDARIN_CN) is False


def test_is_plausible_text_accepts_latin_letters_for_french():
    assert dedup.is_plausible_text("Bonjour", Language.FRENCH) is True


def test_is_plausible_text_rejects_cjk_for_latin_language():
    assert dedup.is_plausible_text("這是一句話", Language.FRENCH) is False


def test_is_plausible_text_rejects_symbols_only_for_latin_language():
    assert dedup.is_plausible_text("000", Language.ENGLISH_US) is False
    assert dedup.is_plausible_text("）", Language.ENGLISH_US) is False
