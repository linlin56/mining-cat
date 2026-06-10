import shutil
import pytest
import chinese_converter
from shared import MOCK_SRT_CN, MOCK_SRT_TW, skip_if_no_srt_cn, skip_if_no_srt_tw

# Expected subtitle text lines after each conversion.
# Characters: 里 = 裡 (s2tw) vs 裏 (s2t).
# Punctuation: " " = 「 」 (s2traditional) and 「 」 = " " (tw2s).
EXPECTED_S2TW = [
    "你好。",
    "我是測試文件。",
    "我是用來測試軟件是否正常運行的。",
    "「這是一句非常有趣的句子，裡面包含了標點符號。」",
]

EXPECTED_S2T = [
    "你好。",
    "我是測試文件。",
    "我是用來測試軟件是否正常運行的。",
    "「這是一句非常有趣的句子，裏面包含了標點符號。」",
]

EXPECTED_TW2S = [
    "你好。",
    "我是测试档案。",
    "我是用来测试软体是否正常运作的。",
    "“这是一句非常有趣的句子，里面包含了标点符号。”",
]


@pytest.fixture
def cn_srt_dir(tmp_path):
    shutil.copy(MOCK_SRT_CN, tmp_path / MOCK_SRT_CN.name)
    return tmp_path


@pytest.fixture
def tw_srt_dir(tmp_path):
    shutil.copy(MOCK_SRT_TW, tmp_path / MOCK_SRT_TW.name)
    return tmp_path


@skip_if_no_srt_cn
def test_s_to_tw(cn_srt_dir, monkeypatch):
    # Simplified to Traditional Taiwan (s2tw).
    monkeypatch.setattr(chinese_converter, "DIR_SRT", cn_srt_dir)
    chinese_converter.convert_srt_dir("s", "tw")

    converted = (cn_srt_dir / MOCK_SRT_CN.name).read_text(encoding="utf-8")
    for line in EXPECTED_S2TW:
        assert line in converted, f"s2tw: expected line not found: {line!r}"


@skip_if_no_srt_cn
def test_s_to_t(cn_srt_dir, monkeypatch):
    # Simplified to Traditional Chinese (s2t).
    monkeypatch.setattr(chinese_converter, "DIR_SRT", cn_srt_dir)
    chinese_converter.convert_srt_dir("s", "t")

    converted = (cn_srt_dir / MOCK_SRT_CN.name).read_text(encoding="utf-8")
    for line in EXPECTED_S2T:
        assert line in converted, f"s2t: expected line not found: {line!r}"


@skip_if_no_srt_tw
def test_tw_to_s(tw_srt_dir, monkeypatch):
    # Traditional Taiwan to Simplified (tw2s).
    monkeypatch.setattr(chinese_converter, "DIR_SRT", tw_srt_dir)
    chinese_converter.convert_srt_dir("tw", "s")

    converted = (tw_srt_dir / MOCK_SRT_TW.name).read_text(encoding="utf-8")
    for line in EXPECTED_TW2S:
        assert line in converted, f"tw2s: expected line not found: {line!r}"


@skip_if_no_srt_cn
def test_no_conversion_s(cn_srt_dir, monkeypatch):
    # source == target (s) : file must remain untouched.
    srt = cn_srt_dir / MOCK_SRT_CN.name
    original = srt.read_text(encoding="utf-8")
    monkeypatch.setattr(chinese_converter, "DIR_SRT", cn_srt_dir)

    chinese_converter.convert_srt_dir("s", "s")

    assert srt.read_text(encoding="utf-8") == original


@skip_if_no_srt_tw
def test_no_conversion_tw(tw_srt_dir, monkeypatch):
    # source == target (tw) : file must remain untouched.
    srt = tw_srt_dir / MOCK_SRT_TW.name
    original = srt.read_text(encoding="utf-8")
    monkeypatch.setattr(chinese_converter, "DIR_SRT", tw_srt_dir)

    chinese_converter.convert_srt_dir("tw", "tw")

    assert srt.read_text(encoding="utf-8") == original


def test_invalid_pair_raises():
    # Unsupported conversion pair must raise ValueError.
    with pytest.raises(ValueError):
        chinese_converter.convert_srt_dir("tw", "t")
