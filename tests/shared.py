import pytest
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"
MOCK_EPUB = MOCK_DIR / "book_zh-TW.epub"
# Decorator to skip tests that require the mock EPUB file if it doesn't exist.
skip_if_no_epub = pytest.mark.skipif(
    not MOCK_EPUB.exists(),
    reason="tests/mock/book_zh-TW.epub not available"
)
