import pytest
from unittest.mock import patch, MagicMock
import align
from align import Segment, save_srt, fix_leading_punct, fix_trailing_opening_punct, restore_opening_punct, prepare_text, _extract_segments, get_device
from language import Language


def test_run_exits_if_no_audio_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", tmp_path / "text")
    with pytest.raises(SystemExit):
        align.run()


def test_run_exits_if_no_text_dir(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", tmp_path / "nonexistent")
    with pytest.raises(SystemExit):
        align.run()


def test_run_only_ch_sets_from_ch(tmp_path, monkeypatch):
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", tmp_path / "text")
    with pytest.raises(SystemExit):
        align.run(only_ch=2)


# --- get_device ---

def test_get_device_returns_valid_string():
    result = get_device()
    assert result in ("cpu", "cuda")


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


# --- _extract_segments ---

def test_extract_segments_attr_style():
    class FakeSeg:
        start = 0.0
        end = 1.0
        text = "Hello"

    class FakeResult:
        segments = [FakeSeg()]

    segs = _extract_segments(FakeResult(), Language.ENGLISH_US)
    assert len(segs) == 1
    assert segs[0].text == "Hello"
    assert segs[0].start == 0.0
    assert segs[0].end == 1.0


def test_extract_segments_dict_style():
    fake = {"segments": [{"start": 0.5, "end": 2.0, "text": "World"}]}
    segs = _extract_segments(fake, Language.ENGLISH_US)
    assert len(segs) == 1
    assert segs[0].text == "World"


def test_extract_segments_skips_empty_text():
    fake = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "   "},
        {"start": 1.0, "end": 2.0, "text": "Valid"},
    ]}
    segs = _extract_segments(fake, Language.ENGLISH_US)
    assert len(segs) == 1
    assert segs[0].text == "Valid"


# --- align_chapter / transcribe_chapter ---

def test_align_chapter(tmp_path):
    text_file = tmp_path / "chapter.txt"
    text_file.write_text("Hello world", encoding="utf-8")
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    mock_model = MagicMock()
    mock_model.align.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}

    segs, text_len = align.align_chapter(mock_model, audio_file, text_file, Language.ENGLISH_US)
    assert text_len == len("Hello world")
    assert len(segs) == 1
    assert segs[0].text == "Hello world"


def test_transcribe_chapter(tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": [{"start": 0.0, "end": 2.0, "text": "Test"}]}

    segs = align.transcribe_chapter(mock_model, audio_file, Language.ENGLISH_US)
    assert len(segs) == 1
    assert segs[0].text == "Test"


# --- run_transcribe ---

def test_run_transcribe_exits_if_no_audio_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    monkeypatch.setattr(align, "DIR_SRT", tmp_path / "srt")
    with pytest.raises(SystemExit):
        align.run_transcribe()


def test_run_transcribe_with_only_ch(tmp_path, monkeypatch):
    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", tmp_path / "nonexistent")
    monkeypatch.setattr(align, "DIR_SRT", tmp_path / "srt")
    with pytest.raises(SystemExit):
        align.run_transcribe(only_ch=1)


def test_run_transcribe_processes_chapter(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    srt_dir = tmp_path / "srt"
    (audio_dir / "chapter_001.mp3").touch()

    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_SRT", srt_dir)

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}]}

    with patch("stable_whisper.load_model", return_value=mock_model):
        align.run_transcribe(model_name="tiny", only_ch=1)

    assert (srt_dir / "chapter_001.srt").exists()


def test_run_transcribe_skips_existing(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    srt_dir = tmp_path / "srt"
    srt_dir.mkdir()
    (audio_dir / "chapter_001.mp3").touch()
    (srt_dir / "chapter_001.srt").write_text("existing")

    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_SRT", srt_dir)

    mock_model = MagicMock()
    with patch("stable_whisper.load_model", return_value=mock_model):
        align.run_transcribe(model_name="tiny")

    mock_model.transcribe.assert_not_called()


# --- run (full alignment) ---

def test_run_processes_chapter(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    text_dir = tmp_path / "text"
    srt_dir = tmp_path / "srt"
    audio_dir.mkdir()
    text_dir.mkdir()
    (audio_dir / "chapter_001.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("Hello world", encoding="utf-8")

    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(align, "DIR_SRT", srt_dir)

    mock_model = MagicMock()
    mock_model.align.return_value = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}

    with patch("stable_whisper.load_model", return_value=mock_model):
        align.run(model_name="tiny", only_ch=1)

    assert (srt_dir / "chapter_001.srt").exists()


def test_run_skips_existing_srt(tmp_path, monkeypatch):
    audio_dir = tmp_path / "audio"
    text_dir = tmp_path / "text"
    srt_dir = tmp_path / "srt"
    audio_dir.mkdir()
    text_dir.mkdir()
    srt_dir.mkdir()
    (audio_dir / "chapter_001.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("Hello", encoding="utf-8")
    (srt_dir / "chapter_001.srt").write_text("existing")

    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(align, "DIR_SRT", srt_dir)

    mock_model = MagicMock()
    with patch("stable_whisper.load_model", return_value=mock_model):
        align.run(model_name="tiny")

    mock_model.align.assert_not_called()


def test_run_warns_on_count_mismatch(tmp_path, monkeypatch, capsys):
    audio_dir = tmp_path / "audio"
    text_dir = tmp_path / "text"
    srt_dir = tmp_path / "srt"
    audio_dir.mkdir()
    text_dir.mkdir()
    (audio_dir / "chapter_001.mp3").touch()
    (audio_dir / "chapter_002.mp3").touch()
    (text_dir / "chapter_001.txt").write_text("A", encoding="utf-8")

    monkeypatch.setattr(align, "DIR_CHAPTERS_AUDIO", audio_dir)
    monkeypatch.setattr(align, "DIR_CHAPTERS_TEXT", text_dir)
    monkeypatch.setattr(align, "DIR_SRT", srt_dir)

    mock_model = MagicMock()
    mock_model.align.return_value = {"segments": []}
    with patch("stable_whisper.load_model", return_value=mock_model):
        align.run(model_name="tiny")

    out = capsys.readouterr().out
    assert "Warning" in out
