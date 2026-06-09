import re
import pytest
from language import Language


# vocab_annotation_pattern :

MANDARIN_PATTERN = re.compile(Language.MANDARIN_TW.value.vocab_annotation_pattern)
JAPANESE_PATTERN = re.compile(Language.JAPANESE.value.vocab_annotation_pattern)

@pytest.mark.parametrize("text,expected", [
    ("學習[1]很重要", "學習很重要"),
    ("一[12]二[345]三", "一二三"),
    ("沒有標記", "沒有標記"),
    ("[1]開頭", "開頭"),
    ("結尾[99]", "結尾"),
])
def test_mandarin_vocab_annotation_pattern(text, expected):
    assert MANDARIN_PATTERN.sub("", text) == expected


@pytest.mark.parametrize("text", [
    "学习很重要",       # no annotation
    "[abc]",           # letters, not digits - should NOT match
    "[ 1]",            # space before digit - should NOT match
])
def test_mandarin_vocab_annotation_no_false_positives(text):
    assert MANDARIN_PATTERN.sub("", text) == text


@pytest.mark.parametrize("text,expected", [
    ("本文［＃「」は二重山括弧に変える］終わり", "本文終わり"),
    ("始め［＃ここから太字］本文［＃ここで太字終わり］", "始め本文"),
    ("アノテーションなし", "アノテーションなし"),
    ("［＃改ページ］", ""),
])
def test_japanese_vocab_annotation_pattern(text, expected):
    assert JAPANESE_PATTERN.sub("", text) == expected


@pytest.mark.parametrize("text", [
    "[＃半角bracket]",    # opening bracket is ASCII - should NOT match
    "［＃",               # unclosed - should NOT match (no closing ］)
    "普通のテキスト",
])
def test_japanese_vocab_annotation_no_false_positives(text):
    assert JAPANESE_PATTERN.sub("", text) == text


# iso639_2 used for subtitles in mp4

def test_iso639_2_values():
    assert Language.MANDARIN_TW.value.iso639_2 == "zho"
    assert Language.MANDARIN_CN.value.iso639_2 == "zho"
    assert Language.JAPANESE.value.iso639_2 == "jpn"
    assert Language.FRENCH.value.iso639_2 == "fra"
    assert Language.ENGLISH_US.value.iso639_2 == "eng"
    assert Language.ENGLISH_UK.value.iso639_2 == "eng"


# from_id / from_label / ids / all_labels

def test_from_id_case_insensitive():
    assert Language.from_id("japanese") is Language.JAPANESE
    assert Language.from_id("JAPANESE") is Language.JAPANESE
    assert Language.from_id("mandarin_tw") is Language.MANDARIN_TW
    assert Language.from_id("MANDARIN_TW") is Language.MANDARIN_TW
    assert Language.from_id("mandarin_cn") is Language.MANDARIN_CN
    assert Language.from_id("MANDARIN_CN") is Language.MANDARIN_CN
    assert Language.from_id("french") is Language.FRENCH
    assert Language.from_id("FRENCH") is Language.FRENCH
    assert Language.from_id("english_us") is Language.ENGLISH_US
    assert Language.from_id("ENGLISH_US") is Language.ENGLISH_US
    assert Language.from_id("english_uk") is Language.ENGLISH_UK
    assert Language.from_id("ENGLISH_UK") is Language.ENGLISH_UK


def test_from_id_unknown_raises():
    with pytest.raises(ValueError, match="Unknown language id"):
        Language.from_id("dothraki")


def test_from_label():
    assert Language.from_label("Japanese") is Language.JAPANESE
    assert Language.from_label("French") is Language.FRENCH
    assert Language.from_label("Mandarin - Taiwan (Traditionnal)") is Language.MANDARIN_TW


def test_from_label_unknown_raises():
    with pytest.raises(ValueError, match="Unknown language label"):
        Language.from_label("Klingon")


def test_all_labels():
    labels = Language.all_labels()
    assert "Japanese" in labels
    assert "French" in labels
    assert len(labels) == len(list(Language))
