import re

import pytest

from miningcat.domain.languages import Language

# vocab_annotation_pattern :

MANDARIN_PATTERN = re.compile(Language.MANDARIN_TW.profile.vocab_annotation_pattern)
JAPANESE_PATTERN = re.compile(Language.JAPANESE.profile.vocab_annotation_pattern)
CANTONESE_PATTERN = re.compile(Language.CANTONESE_HK.profile.vocab_annotation_pattern)

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
    ("學習[1]好緊要", "學習好緊要"),
    ("一[12]二[345]三", "一二三"),
    ("冇標記", "冇標記"),
    ("[1]開頭", "開頭"),
    ("結尾[99]", "結尾"),
])
def test_cantonese_vocab_annotation_pattern(text, expected):
    assert CANTONESE_PATTERN.sub("", text) == expected


@pytest.mark.parametrize("text", [
    "學習好緊要",       # no annotation
    "[abc]",           # letters, not digits - should NOT match
    "[ 1]",            # space before digit - should NOT match
])
def test_cantonese_vocab_annotation_no_false_positives(text):
    assert CANTONESE_PATTERN.sub("", text) == text


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
    assert Language.MANDARIN_TW.profile.iso639_2 == "zho"
    assert Language.MANDARIN_CN.profile.iso639_2 == "zho"
    assert Language.JAPANESE.profile.iso639_2 == "jpn"
    assert Language.FRENCH.profile.iso639_2 == "fra"
    assert Language.ENGLISH_US.profile.iso639_2 == "eng"
    assert Language.ENGLISH_UK.profile.iso639_2 == "eng"
    assert Language.ITALIAN.profile.iso639_2 == "ita"
    assert Language.SPANISH.profile.iso639_2 == "spa"
    assert Language.POLISH.profile.iso639_2 == "pol"
    assert Language.KOREAN.profile.iso639_2 == "kor"
    assert Language.GERMAN.profile.iso639_2 == "deu"
    assert Language.PORTUGUESE.profile.iso639_2 == "por"
    assert Language.VIETNAMESE.profile.iso639_2 == "vie"
    assert Language.CANTONESE_HK.profile.iso639_2 == "yue"


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
    assert Language.from_id("italian") is Language.ITALIAN
    assert Language.from_id("ITALIAN") is Language.ITALIAN
    assert Language.from_id("spanish") is Language.SPANISH
    assert Language.from_id("SPANISH") is Language.SPANISH
    assert Language.from_id("polish") is Language.POLISH
    assert Language.from_id("POLISH") is Language.POLISH
    assert Language.from_id("korean") is Language.KOREAN
    assert Language.from_id("KOREAN") is Language.KOREAN
    assert Language.from_id("german") is Language.GERMAN
    assert Language.from_id("GERMAN") is Language.GERMAN
    assert Language.from_id("portuguese") is Language.PORTUGUESE
    assert Language.from_id("PORTUGUESE") is Language.PORTUGUESE
    assert Language.from_id("vietnamese") is Language.VIETNAMESE
    assert Language.from_id("VIETNAMESE") is Language.VIETNAMESE
    assert Language.from_id("cantonese_hk") is Language.CANTONESE_HK
    assert Language.from_id("CANTONESE_HK") is Language.CANTONESE_HK


def test_from_id_unknown_raises():
    with pytest.raises(ValueError, match="Unknown language id"):
        Language.from_id("dothraki")


def test_from_label():
    assert Language.from_label("Japanese") is Language.JAPANESE
    assert Language.from_label("French") is Language.FRENCH
    assert Language.from_label("Mandarin - Taiwan (Traditional)") is Language.MANDARIN_TW


def test_from_label_unknown_raises():
    with pytest.raises(ValueError, match="Unknown language label"):
        Language.from_label("Klingon")


def test_all_labels():
    labels = Language.all_labels()
    assert "Japanese" in labels
    assert "French" in labels
    assert len(labels) == len(list(Language))


# LanguageProfile: built with LanguageProfileBuilder, one per Language

def test_builder_defaults():
    from miningcat.domain.languages import WordSegmentation
    from miningcat.domain.languages.profile_builder import LanguageProfileBuilder
    from miningcat.domain.text import scripts

    profile = (LanguageProfileBuilder("Test").codes(key="xx", whisper="xx", iso639_2="xxx")
               .ocr(apple="xx-XX", easyocr="xx").build())
    assert profile.tag == "xx-XX"  # the Apple OCR code, when no tag is given
    assert profile.youtube_caption_codes == ("xx",)
    assert profile.ocr_script is scripts.LATIN_LETTER
    assert profile.word_segmentation is WordSegmentation.SPACES
    assert profile.voices == () and profile.default_voice is None
    assert profile.closing_punct == frozenset() and profile.script is None


def test_builder_needs_codes_and_ocr():
    from miningcat.domain.languages.profile_builder import LanguageProfileBuilder

    with pytest.raises(ValueError):
        LanguageProfileBuilder("Test").ocr(apple="xx-XX", easyocr="xx").build()
    with pytest.raises(ValueError):
        LanguageProfileBuilder("Test").codes(key="xx", whisper="xx", iso639_2="xxx").build()


def test_every_language_has_voices_and_a_study_language():
    from miningcat.domain.languages import LANGUAGES

    for lang in Language:
        assert lang.profile.voices, lang
        assert lang.profile.key in LANGUAGES, lang
        assert lang.profile.voice_id(lang.profile.default_voice.label) == lang.profile.default_voice.voice_id


def test_variants_of_a_study_language():
    assert Language.variants_of("zh") == [Language.MANDARIN_TW, Language.MANDARIN_CN]
    assert Language.variants_of("en") == [Language.ENGLISH_US, Language.ENGLISH_UK]
    assert Language.variants_of("nan") == [Language.TAIGI]
    assert Language.for_tag("nan-Hant") is Language.TAIGI


@pytest.mark.parametrize("tag,expected", [
    ("zh-Hant", Language.MANDARIN_TW),
    ("zh-Hans", Language.MANDARIN_CN),
    ("zh-CN-x-hans", Language.MANDARIN_CN),
    ("yue-Hant", Language.CANTONESE_HK),
    ("ja", Language.JAPANESE),
    ("en-GB", Language.ENGLISH_UK),
    ("en", Language.ENGLISH_US),
    ("ru", None),
    ("", None),
])
def test_language_for_tag(tag, expected):
    assert Language.for_tag(tag) is expected


def test_ids():
    assert Language.MANDARIN_TW.id == "mandarin_tw"
    assert Language.from_id("Cantonese_HK") is Language.CANTONESE_HK
