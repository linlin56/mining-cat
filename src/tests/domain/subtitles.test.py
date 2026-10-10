from miningcat.domain.languages import Language
from miningcat.domain.subtitles.punctuation import (
    fix_leading_punct,
    fix_trailing_opening_punct,
    prepare_text,
    restore_opening_punct,
)
from miningcat.domain.subtitles.segment import Segment
from miningcat.domain.subtitles.srt import replace_srt_lines, srt_lines
from miningcat.infrastructure.files.srt_files import save_srt

# --- Segment ---

def test_segment_fmt_zero():
    seg = Segment(1, 0.0, 0.0, "")
    assert seg._fmt(0.0) == "00:00:00,000"


def test_segment_fmt_hms():
    seg = Segment(1, 0.0, 0.0, "")
    assert seg._fmt(3661.5) == "01:01:01,500"


def test_segment_to_srt():
    seg = Segment(3, 1.0, 2.5, "Hello")
    srt = seg.to_srt()
    assert srt.startswith("3\n")
    assert "00:00:01,000 --> 00:00:02,500" in srt
    assert "Hello" in srt


# --- save_srt ---

def test_save_srt_writes_content(tmp_path):
    segs = [Segment(0, 0.0, 1.0, "A"), Segment(0, 1.0, 2.0, "B")]
    out = tmp_path / "out.srt"
    save_srt(segs, out)
    content = out.read_text(encoding="utf-8")
    assert "1\n" in content
    assert "2\n" in content
    assert "A" in content
    assert "B" in content


def test_save_srt_creates_parent_dirs(tmp_path):
    segs = [Segment(0, 0.0, 1.0, "X")]
    out = tmp_path / "sub" / "out.srt"
    save_srt(segs, out)
    assert out.exists()


# --- fix_leading_punct ---

def test_fix_leading_punct_no_leading():
    segs = [Segment(1, 0.0, 1.0, "你好"), Segment(2, 1.0, 2.0, "世界")]
    result = fix_leading_punct(segs, Language.MANDARIN_TW)
    assert len(result) == 2
    assert result[0].text == "你好"
    assert result[1].text == "世界"


def test_fix_leading_punct_moves_to_prev():
    segs = [Segment(1, 0.0, 1.0, "你好"), Segment(2, 1.0, 2.0, "。世界")]
    result = fix_leading_punct(segs, Language.MANDARIN_TW)
    assert result[0].text == "你好。"
    assert result[1].text == "世界"


def test_fix_leading_punct_only_punct_no_remainder():
    segs = [Segment(1, 0.0, 1.0, "你好"), Segment(2, 1.0, 2.0, "。")]
    result = fix_leading_punct(segs, Language.MANDARIN_TW)
    assert len(result) == 1
    assert result[0].text == "你好。"


def test_fix_leading_punct_first_seg_unchanged():
    segs = [Segment(1, 0.0, 1.0, "。你好")]
    result = fix_leading_punct(segs, Language.MANDARIN_TW)
    assert len(result) == 1
    assert result[0].text == "。你好"


# --- fix_trailing_opening_punct ---

def test_fix_trailing_opening_punct_no_opening():
    segs = [Segment(1, 0.0, 1.0, "Hola."), Segment(2, 1.0, 2.0, "¿Cómo estás?")]
    result = fix_trailing_opening_punct(segs, Language.SPANISH)
    assert result[0].text == "Hola."
    assert result[1].text == "¿Cómo estás?"


def test_fix_trailing_opening_punct_moves_to_next():
    segs = [Segment(1, 0.0, 1.0, "Hola. ¿"), Segment(2, 1.0, 2.0, "Cómo estás?")]
    result = fix_trailing_opening_punct(segs, Language.SPANISH)
    assert result[0].text == "Hola."
    assert result[1].text == "¿Cómo estás?"


def test_fix_trailing_opening_punct_only_opening_dropped():
    segs = [Segment(1, 0.0, 1.0, "¿"), Segment(2, 1.0, 2.0, "Cómo estás?")]
    result = fix_trailing_opening_punct(segs, Language.SPANISH)
    assert len(result) == 1
    assert result[0].text == "¿Cómo estás?"


def test_fix_trailing_opening_punct_noop_for_language_without_opening():
    segs = [Segment(1, 0.0, 1.0, "Hello."), Segment(2, 1.0, 2.0, "World.")]
    result = fix_trailing_opening_punct(segs, Language.ENGLISH_US)
    assert result == segs


# --- restore_opening_punct ---

def test_restore_opening_punct_adds_missing_inverted_question():
    ref = "conducir al revés. ¿Quieres intentarlo?"
    segs = [Segment(1, 0.0, 1.0, "conducir al revés."), Segment(2, 1.0, 2.0, "Quieres intentarlo?")]
    result = restore_opening_punct(segs, ref, Language.SPANISH)
    assert result[1].text == "¿Quieres intentarlo?"


def test_restore_opening_punct_no_change_when_already_present():
    ref = "Hola. ¿Cómo estás?"
    segs = [Segment(1, 0.0, 1.0, "Hola."), Segment(2, 1.0, 2.0, "¿Cómo estás?")]
    result = restore_opening_punct(segs, ref, Language.SPANISH)
    assert result[1].text == "¿Cómo estás?"


def test_restore_opening_punct_noop_without_opening_punct():
    ref = "Hello. How are you?"
    segs = [Segment(1, 0.0, 1.0, "Hello."), Segment(2, 1.0, 2.0, "How are you?")]
    result = restore_opening_punct(segs, ref, Language.ENGLISH_US)
    assert result[1].text == "How are you?"


def test_restore_opening_punct_multiple_questions():
    ref = "Texto. ¿Primera pregunta? ¡Exclamación! ¿Segunda pregunta?"
    segs = [
        Segment(1, 0.0, 1.0, "Texto."),
        Segment(2, 1.0, 2.0, "Primera pregunta?"),
        Segment(3, 2.0, 3.0, "Exclamación!"),
        Segment(4, 3.0, 4.0, "Segunda pregunta?"),
    ]
    result = restore_opening_punct(segs, ref, Language.SPANISH)
    assert result[1].text == "¿Primera pregunta?"
    assert result[2].text == "¡Exclamación!"
    assert result[3].text == "¿Segunda pregunta?"


# --- prepare_text ---

def test_prepare_text_strips_mandarin_annotations():
    raw = "學習[1]很重要\n\n一[12]二"
    result = prepare_text(raw, Language.MANDARIN_TW)
    assert result == "學習很重要\n一二"


def test_prepare_text_removes_blank_lines():
    raw = "Line one\n\n\nLine two"
    result = prepare_text(raw, Language.ENGLISH_US)
    assert result == "Line one\nLine two"


def test_prepare_text_strips_japanese_annotations():
    raw = "本文［＃改ページ］続き"
    result = prepare_text(raw, Language.JAPANESE)
    assert result == "本文続き"


# --- translated SRT: the same numbers, timestamps and formatting

SRT_TO_TRANSLATE = """1
00:00:01,000 --> 00:00:02,500
<i>你好</i>

2
00:00:03,000 --> 00:00:04,000
{\\an8}- 你好
- 再見

3
00:00:05,000 --> 00:00:06,000
<font color="red">我</font>們走
"""


def test_srt_lines_without_formatting_each_once():
    assert srt_lines(SRT_TO_TRANSLATE) == ["你好", "再見", "我們走"]


def test_replace_srt_lines_keeps_the_rest():
    translated = replace_srt_lines(SRT_TO_TRANSLATE.replace("\n", "\r\n"), {"你好": "Hello", "再見": "Bye", "我們走": "Let's go"})
    assert translated == """1
00:00:01,000 --> 00:00:02,500
<i>Hello</i>

2
00:00:03,000 --> 00:00:04,000
{\\an8}- Hello
- Bye

3
00:00:05,000 --> 00:00:06,000
Let's go
"""
