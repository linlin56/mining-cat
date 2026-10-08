"""Writing systems, as regular expressions matching one character."""
import re

# CJK ideographs, hiragana and katakana (half-width katakana included).
CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uff66-\uff9f]")
# Hangul syllables and compatibility jamo.
HANGUL = re.compile(r"[\uac00-\ud7a3\u3131-\u314e\u314f-\u3163]")
LATIN_LETTER = re.compile(r"[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff]")

# Chinese characters (CJK and extension A), as counted in character lists.
HAN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
# Chinese characters, hiragana and katakana: what a Japanese character list counts.
HAN_AND_KANA = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]")

# One Chinese character or kanji (CJK, extension A, compatibility ideographs and the supplementary planes).
HAN_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff]")
