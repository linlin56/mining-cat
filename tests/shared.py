import pytest
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"
MOCK_EPUB_TW = MOCK_DIR / "book_zh-TW.epub"
MOCK_EPUB_CN = MOCK_DIR / "book_zh-CN.epub"

skip_if_no_epub_tw = pytest.mark.skipif(
    not MOCK_EPUB_TW.exists(),
    reason="tests/mock/book_zh-TW.epub not available"
)
skip_if_no_epub_cn = pytest.mark.skipif(
    not MOCK_EPUB_CN.exists(),
    reason="tests/mock/book_zh-CN.epub not available"
)
