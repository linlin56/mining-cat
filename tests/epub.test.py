import epub
from shared import MOCK_DIR, skip_if_no_epub

# Lines from tests/mock/README.md — the known content of book_zh-TW.epub
EXPECTED_LINES = [
    "你好。",
    "我是測試檔案。",
    "我是用來測試軟體是否正常運作的。",
    "「這是一句非常有趣的句子，裡面包含了標點符號。」",
]


@skip_if_no_epub
def test_run_list_only(tmp_path, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", MOCK_DIR)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", tmp_path / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", tmp_path / "temp")
    epub.run(list_only=True)
    assert not (tmp_path / "chapters_text").exists()


@skip_if_no_epub
def test_run_saves_chapters(tmp_path, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", MOCK_DIR)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", tmp_path / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", tmp_path / "temp")
    epub.run()
    assert (tmp_path / "chapters_text").exists()
    assert len(list((tmp_path / "chapters_text").glob("chapter_*.txt"))) > 0


@skip_if_no_epub
def test_run_chapter_content(tmp_path, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", MOCK_DIR)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", tmp_path / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", tmp_path / "temp")
    epub.run()

    all_text = "".join(
        f.read_text(encoding="utf-8")
        for f in sorted((tmp_path / "chapters_text").glob("chapter_*.txt"))
    )
    for line in EXPECTED_LINES:
        assert line in all_text, f"Expected line not found in output: {line!r}"
