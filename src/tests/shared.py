import pytest
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"
MOCK_EPUB_TW = MOCK_DIR / "book_zh-TW.epub"
MOCK_EPUB_CN = MOCK_DIR / "book_zh-CN.epub"
MOCK_EPUB_JA = MOCK_DIR / "book_ja.epub"
MOCK_TXT_TW  = MOCK_DIR / "book_zh-TW.txt"
MOCK_TXT_CN  = MOCK_DIR / "book_zh-CN.txt"
MOCK_TXT_JA  = MOCK_DIR / "book_ja.txt"
MOCK_EPUB_FR = MOCK_DIR / "book_fr.epub"
MOCK_TXT_FR  = MOCK_DIR / "book_fr.txt"
MOCK_EPUB_EN_US = MOCK_DIR / "book_en-US.epub"
MOCK_TXT_EN_US  = MOCK_DIR / "book_en-US.txt"
MOCK_EPUB_EN_GB = MOCK_DIR / "book_en-GB.epub"
MOCK_TXT_EN_GB  = MOCK_DIR / "book_en-GB.txt"
MOCK_SRT_CN = MOCK_DIR / "srt_zh-CN.srt"
MOCK_SRT_TW = MOCK_DIR / "srt_zh-TW.srt"
MOCK_SRT_JA = MOCK_DIR / "srt_ja.srt"
MOCK_SRT_FR = MOCK_DIR / "srt_fr.srt"
MOCK_SRT_EN_US = MOCK_DIR / "srt_en-US.srt"
MOCK_SRT_EN_GB = MOCK_DIR / "srt_en-GB.srt"
MOCK_EPUB_IT = MOCK_DIR / "book_it.epub"
MOCK_TXT_IT  = MOCK_DIR / "book_it.txt"
MOCK_SRT_IT  = MOCK_DIR / "srt_it.srt"
MOCK_EPUB_ES = MOCK_DIR / "book_es.epub"
MOCK_TXT_ES  = MOCK_DIR / "book_es.txt"
MOCK_SRT_ES  = MOCK_DIR / "srt_es.srt"

skip_if_no_epub_tw = pytest.mark.skipif(
    not MOCK_EPUB_TW.exists(),
    reason="tests/mock/book_zh-TW.epub not available"
)
skip_if_no_epub_cn = pytest.mark.skipif(
    not MOCK_EPUB_CN.exists(),
    reason="tests/mock/book_zh-CN.epub not available"
)
skip_if_no_epub_ja = pytest.mark.skipif(
    not MOCK_EPUB_JA.exists(),
    reason="tests/mock/book_ja.epub not available"
)
skip_if_no_txt_tw = pytest.mark.skipif(
    not MOCK_TXT_TW.exists(),
    reason="tests/mock/book_zh-TW.txt not available"
)
skip_if_no_txt_cn = pytest.mark.skipif(
    not MOCK_TXT_CN.exists(),
    reason="tests/mock/book_zh-CN.txt not available"
)
skip_if_no_txt_ja = pytest.mark.skipif(
    not MOCK_TXT_JA.exists(),
    reason="tests/mock/book_ja.txt not available"
)
skip_if_no_srt_cn = pytest.mark.skipif(
    not MOCK_SRT_CN.exists(),
    reason="tests/mock/srt_zh-CN.srt not available"
)
skip_if_no_srt_tw = pytest.mark.skipif(
    not MOCK_SRT_TW.exists(),
    reason="tests/mock/srt_zh-TW.srt not available"
)
skip_if_no_srt_ja = pytest.mark.skipif(
    not MOCK_SRT_JA.exists(),
    reason="tests/mock/srt_ja.srt not available"
)
skip_if_no_epub_fr = pytest.mark.skipif(
    not MOCK_EPUB_FR.exists(),
    reason="tests/mock/book_fr.epub not available"
)
skip_if_no_txt_fr = pytest.mark.skipif(
    not MOCK_TXT_FR.exists(),
    reason="tests/mock/book_fr.txt not available"
)
skip_if_no_srt_fr = pytest.mark.skipif(
    not MOCK_SRT_FR.exists(),
    reason="tests/mock/srt_fr.srt not available"
)
skip_if_no_epub_en_us = pytest.mark.skipif(
    not MOCK_EPUB_EN_US.exists(),
    reason="tests/mock/book_en-US.epub not available"
)
skip_if_no_txt_en_us = pytest.mark.skipif(
    not MOCK_TXT_EN_US.exists(),
    reason="tests/mock/book_en-US.txt not available"
)
skip_if_no_srt_en_us = pytest.mark.skipif(
    not MOCK_SRT_EN_US.exists(),
    reason="tests/mock/srt_en-US.srt not available"
)
skip_if_no_epub_en_gb = pytest.mark.skipif(
    not MOCK_EPUB_EN_GB.exists(),
    reason="tests/mock/book_en-GB.epub not available"
)
skip_if_no_txt_en_gb = pytest.mark.skipif(
    not MOCK_TXT_EN_GB.exists(),
    reason="tests/mock/book_en-GB.txt not available"
)
skip_if_no_srt_en_gb = pytest.mark.skipif(
    not MOCK_SRT_EN_GB.exists(),
    reason="tests/mock/srt_en-GB.srt not available"
)
skip_if_no_epub_it = pytest.mark.skipif(
    not MOCK_EPUB_IT.exists(),
    reason="tests/mock/book_it.epub not available"
)
skip_if_no_txt_it = pytest.mark.skipif(
    not MOCK_TXT_IT.exists(),
    reason="tests/mock/book_it.txt not available"
)
skip_if_no_srt_it = pytest.mark.skipif(
    not MOCK_SRT_IT.exists(),
    reason="tests/mock/srt_it.srt not available"
)
skip_if_no_epub_es = pytest.mark.skipif(
    not MOCK_EPUB_ES.exists(),
    reason="tests/mock/book_es.epub not available"
)
skip_if_no_txt_es = pytest.mark.skipif(
    not MOCK_TXT_ES.exists(),
    reason="tests/mock/book_es.txt not available"
)
skip_if_no_srt_es = pytest.mark.skipif(
    not MOCK_SRT_ES.exists(),
    reason="tests/mock/srt_es.srt not available"
)
