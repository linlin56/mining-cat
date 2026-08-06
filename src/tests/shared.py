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
MOCK_EPUB_PL = MOCK_DIR / "book_pl.epub"
MOCK_TXT_PL  = MOCK_DIR / "book_pl.txt"
MOCK_SRT_PL  = MOCK_DIR / "srt_pl.srt"
MOCK_EPUB_KO = MOCK_DIR / "book_ko.epub"
MOCK_TXT_KO  = MOCK_DIR / "book_ko.txt"
MOCK_SRT_KO  = MOCK_DIR / "srt_ko.srt"
MOCK_EPUB_DE = MOCK_DIR / "book_de.epub"
MOCK_TXT_DE  = MOCK_DIR / "book_de.txt"
MOCK_SRT_DE  = MOCK_DIR / "srt_de.srt"
MOCK_EPUB_PT = MOCK_DIR / "book_pt.epub"
MOCK_TXT_PT  = MOCK_DIR / "book_pt.txt"
MOCK_SRT_PT  = MOCK_DIR / "srt_pt.srt"
MOCK_EPUB_VI = MOCK_DIR / "book_vi.epub"
MOCK_TXT_VI  = MOCK_DIR / "book_vi.txt"
MOCK_SRT_VI  = MOCK_DIR / "srt_vi.srt"
MOCK_EPUB_YUE_HK = MOCK_DIR / "book_yue-HK.epub"
MOCK_TXT_YUE_HK  = MOCK_DIR / "book_yue-HK.txt"
MOCK_SRT_YUE_HK  = MOCK_DIR / "srt_yue-HK.srt"

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
skip_if_no_epub_pl = pytest.mark.skipif(
    not MOCK_EPUB_PL.exists(),
    reason="tests/mock/book_pl.epub not available"
)
skip_if_no_txt_pl = pytest.mark.skipif(
    not MOCK_TXT_PL.exists(),
    reason="tests/mock/book_pl.txt not available"
)
skip_if_no_srt_pl = pytest.mark.skipif(
    not MOCK_SRT_PL.exists(),
    reason="tests/mock/srt_pl.srt not available"
)
skip_if_no_epub_ko = pytest.mark.skipif(
    not MOCK_EPUB_KO.exists(),
    reason="tests/mock/book_ko.epub not available"
)
skip_if_no_txt_ko = pytest.mark.skipif(
    not MOCK_TXT_KO.exists(),
    reason="tests/mock/book_ko.txt not available"
)
skip_if_no_srt_ko = pytest.mark.skipif(
    not MOCK_SRT_KO.exists(),
    reason="tests/mock/srt_ko.srt not available"
)
skip_if_no_epub_de = pytest.mark.skipif(
    not MOCK_EPUB_DE.exists(),
    reason="tests/mock/book_de.epub not available"
)
skip_if_no_txt_de = pytest.mark.skipif(
    not MOCK_TXT_DE.exists(),
    reason="tests/mock/book_de.txt not available"
)
skip_if_no_srt_de = pytest.mark.skipif(
    not MOCK_SRT_DE.exists(),
    reason="tests/mock/srt_de.srt not available"
)
skip_if_no_epub_pt = pytest.mark.skipif(
    not MOCK_EPUB_PT.exists(),
    reason="tests/mock/book_pt.epub not available"
)
skip_if_no_txt_pt = pytest.mark.skipif(
    not MOCK_TXT_PT.exists(),
    reason="tests/mock/book_pt.txt not available"
)
skip_if_no_srt_pt = pytest.mark.skipif(
    not MOCK_SRT_PT.exists(),
    reason="tests/mock/srt_pt.srt not available"
)
skip_if_no_epub_vi = pytest.mark.skipif(
    not MOCK_EPUB_VI.exists(),
    reason="tests/mock/book_vi.epub not available"
)
skip_if_no_txt_vi = pytest.mark.skipif(
    not MOCK_TXT_VI.exists(),
    reason="tests/mock/book_vi.txt not available"
)
skip_if_no_srt_vi = pytest.mark.skipif(
    not MOCK_SRT_VI.exists(),
    reason="tests/mock/srt_vi.srt not available"
)
skip_if_no_epub_yue_hk = pytest.mark.skipif(
    not MOCK_EPUB_YUE_HK.exists(),
    reason="tests/mock/book_yue-HK.epub not available"
)
skip_if_no_txt_yue_hk = pytest.mark.skipif(
    not MOCK_TXT_YUE_HK.exists(),
    reason="tests/mock/book_yue-HK.txt not available"
)
skip_if_no_srt_yue_hk = pytest.mark.skipif(
    not MOCK_SRT_YUE_HK.exists(),
    reason="tests/mock/srt_yue-HK.srt not available"
)
