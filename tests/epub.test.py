import shutil
import pytest
import epub
from shared import MOCK_EPUB_TW, MOCK_EPUB_CN, skip_if_no_epub_tw, skip_if_no_epub_cn

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

EPUB_PARAMS = [
    pytest.param(MOCK_EPUB_TW, marks=skip_if_no_epub_tw, id="zh-TW"),
    pytest.param(MOCK_EPUB_CN, marks=skip_if_no_epub_cn, id="zh-CN"),
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
