"""Word frequency lists: the words of a text and their number of occurrences."""
import re
from collections import Counter

from miningcat.domain.languages import Language, WordSegmentation
from miningcat.domain.text import taigi


def _segment_chinese(text: str) -> list[str]:
    import jieba
    text = re.sub(r"[^一-鿿㐀-䶿]", " ", text)
    return list(jieba.cut(text))


def _segment_japanese(text: str) -> list[str]:
    from janome.tokenizer import Tokenizer
    t = Tokenizer()
    return [token.surface for token in t.tokenize(text)]


# Hanji words (taibun's tokenizer) and romanized words (tsia̍h-pn̄g), keeping the tone marks.
def _segment_taigi(text: str) -> list[str]:
    return taigi.tokenize(text)


def _segment_generic(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text, re.UNICODE)


_SEGMENTERS = {
    WordSegmentation.CHINESE: _segment_chinese,
    WordSegmentation.JAPANESE: _segment_japanese,
    WordSegmentation.TAIGI: _segment_taigi,
    WordSegmentation.SPACES: _segment_generic,
}


def compute(text: str, language: Language, min_length: int = 1) -> Counter:
    segment = _SEGMENTERS[language.profile.word_segmentation]
    words = segment(text)
    return Counter(w for w in words if len(w) >= min_length and w.strip())


def total_count(counter: Counter) -> int:
    """Total number of word occurrences (tokens), not unique words."""
    return sum(counter.values())
