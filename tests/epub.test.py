import pytest
from pathlib import Path
import epub

MOCK_DIR = Path(__file__).parent / "mock"
MOCK_EPUB = MOCK_DIR / "book.epub"

skip_if_no_epub = pytest.mark.skipif(
    not MOCK_EPUB.exists(),
    reason="tests/mock/book.epub not available"
)


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
