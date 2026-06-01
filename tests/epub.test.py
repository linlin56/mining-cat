import shutil
import pytest
import epub
from shared import (
    MOCK_EPUB_TW, MOCK_EPUB_CN, MOCK_EPUB_JA,
    skip_if_no_epub_tw, skip_if_no_epub_cn, skip_if_no_epub_ja,
    MOCK_TXT_TW, MOCK_TXT_CN, MOCK_TXT_JA,
    skip_if_no_txt_tw, skip_if_no_txt_cn, skip_if_no_txt_ja,
    MOCK_SRT_JA, skip_if_no_srt_ja,
)

EXPECTED_LINES_TW = [
    "你好。",
    "我是測試檔案。",
    "我是用來測試軟體是否正常運作的。",
    "「這是一句非常有趣的句子，裡面包含了標點符號。」",
]

EXPECTED_LINES_CN = [
    "你好。",
    "我是测试文件。",
    "我是用来测试软件是否正常运行的。",
    "“这是一句非常有趣的句子，里面包含了标点符号。”",
]

EXPECTED_LINES_JA = [
    "こんにちは。",
    "私はテストファイルです。",
    "ソフトウェアが正常に動作するかをテストするために使われます。",
    "「これはとても興味深い文で、句読点が含まれています。」",
]

EPUB_PARAMS = [
    pytest.param(MOCK_EPUB_TW, marks=skip_if_no_epub_tw, id="zh-TW"),
    pytest.param(MOCK_EPUB_CN, marks=skip_if_no_epub_cn, id="zh-CN"),
    pytest.param(MOCK_EPUB_JA, marks=skip_if_no_epub_ja, id="ja"),
]


@pytest.fixture
def epub_dir(tmp_path, request):
    epub_src = request.param
    shutil.copy(epub_src, tmp_path / epub_src.name)
    return tmp_path


@pytest.mark.parametrize("epub_dir", EPUB_PARAMS, indirect=True)
def test_run_list_only(epub_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run(list_only=True)
    assert not (epub_dir / "chapters_text").exists()


@pytest.mark.parametrize("epub_dir", EPUB_PARAMS, indirect=True)
def test_run_saves_chapters(epub_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run()
    assert (epub_dir / "chapters_text").exists()
    assert len(list((epub_dir / "chapters_text").glob("chapter_*.txt"))) > 0


@pytest.mark.parametrize("epub_dir,expected", [
    pytest.param(MOCK_EPUB_TW, EXPECTED_LINES_TW, marks=skip_if_no_epub_tw, id="zh-TW"),
    pytest.param(MOCK_EPUB_CN, EXPECTED_LINES_CN, marks=skip_if_no_epub_cn, id="zh-CN"),
    pytest.param(MOCK_EPUB_JA, EXPECTED_LINES_JA, marks=skip_if_no_epub_ja, id="ja"),
], indirect=["epub_dir"])
def test_run_chapter_content(epub_dir, expected, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run()

    all_text = "".join(
        f.read_text(encoding="utf-8")
        for f in sorted((epub_dir / "chapters_text").glob("chapter_*.txt"))
    )
    for line in expected:
        assert line in all_text, f"Expected line not found in output: {line!r}"


# TXT tests

TXT_PARAMS = [
    pytest.param(MOCK_TXT_TW, marks=skip_if_no_txt_tw, id="zh-TW"),
    pytest.param(MOCK_TXT_CN, marks=skip_if_no_txt_cn, id="zh-CN"),
    pytest.param(MOCK_TXT_JA, marks=skip_if_no_txt_ja, id="ja"),
]


@pytest.fixture
def txt_dir(tmp_path, request):
    txt_src = request.param
    shutil.copy(txt_src, tmp_path / txt_src.name)
    return tmp_path


@pytest.mark.parametrize("txt_dir", TXT_PARAMS, indirect=True)
def test_txt_list_only(txt_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run(list_only=True)
    assert not (txt_dir / "chapters_text").exists()


@pytest.mark.parametrize("txt_dir", TXT_PARAMS, indirect=True)
def test_txt_saves_single_chapter(txt_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run()
    chapters = sorted((txt_dir / "chapters_text").glob("chapter_*.txt"))
    assert len(chapters) == 1


@pytest.mark.parametrize("txt_dir,expected", [
    pytest.param(MOCK_TXT_TW, EXPECTED_LINES_TW, marks=skip_if_no_txt_tw, id="zh-TW"),
    pytest.param(MOCK_TXT_CN, EXPECTED_LINES_CN, marks=skip_if_no_txt_cn, id="zh-CN"),
    pytest.param(MOCK_TXT_JA, EXPECTED_LINES_JA, marks=skip_if_no_txt_ja, id="ja"),
], indirect=["txt_dir"])
def test_txt_chapter_content(txt_dir, expected, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run()

    all_text = "".join(
        f.read_text(encoding="utf-8")
        for f in sorted((txt_dir / "chapters_text").glob("chapter_*.txt"))
    )
    for line in expected:
        assert line in all_text, f"Expected line not found in output: {line!r}"


# SRT tests

@skip_if_no_srt_ja
def test_srt_ja_segment_count():
    segments = [b for b in MOCK_SRT_JA.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_JA)


@skip_if_no_srt_ja
def test_srt_ja_content():
    text = MOCK_SRT_JA.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_JA:
        assert line in text


@skip_if_no_srt_ja
def test_srt_ja_timecodes():
    timecodes = [l for l in MOCK_SRT_JA.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_JA)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end
