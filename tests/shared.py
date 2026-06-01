import pytest
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"
MOCK_EPUB_TW = MOCK_DIR / "book_zh-TW.epub"
MOCK_EPUB_CN = MOCK_DIR / "book_zh-CN.epub"
MOCK_TXT_TW  = MOCK_DIR / "book_zh-TW.txt"
MOCK_TXT_CN  = MOCK_DIR / "book_zh-CN.txt"
MOCK_SRT_CN = MOCK_DIR / "srt_zh-CN.srt"
MOCK_SRT_TW = MOCK_DIR / "srt_zh-TW.srt"

skip_if_no_epub_tw = pytest.mark.skipif(
    not MOCK_EPUB_TW.exists(),
    reason="tests/mock/book_zh-TW.epub not available"
)
skip_if_no_epub_cn = pytest.mark.skipif(
    not MOCK_EPUB_CN.exists(),
    reason="tests/mock/book_zh-CN.epub not available"
)
skip_if_no_txt_tw = pytest.mark.skipif(
    not MOCK_TXT_TW.exists(),
    reason="tests/mock/book_zh-TW.txt not available"
)
skip_if_no_txt_cn = pytest.mark.skipif(
    not MOCK_TXT_CN.exists(),
    reason="tests/mock/book_zh-CN.txt not available"
)
skip_if_no_srt_cn = pytest.mark.skipif(
    not MOCK_SRT_CN.exists(),
    reason="tests/mock/srt_zh-CN.srt not available"
)
skip_if_no_srt_tw = pytest.mark.skipif(
    not MOCK_SRT_TW.exists(),
    reason="tests/mock/srt_zh-TW.srt not available"
)
