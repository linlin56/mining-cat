import re
from collections import Counter
from pathlib import Path

from miningcat.domain.languages import Language, WordSegmentation


def _segment_chinese(text: str) -> list[str]:
    import jieba
    text = re.sub(r"[^一-鿿㐀-䶿]", " ", text)
    return list(jieba.cut(text))


def _segment_japanese(text: str) -> list[str]:
    from janome.tokenizer import Tokenizer
    t = Tokenizer()
    return [token.surface for token in t.tokenize(text)]


def _segment_generic(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text, re.UNICODE)


_SEGMENTERS = {
    WordSegmentation.CHINESE: _segment_chinese,
    WordSegmentation.JAPANESE: _segment_japanese,
    WordSegmentation.SPACES: _segment_generic,
}


def compute(text: str, language: Language, min_length: int = 1) -> Counter:
    segment = _SEGMENTERS[language.profile.word_segmentation]
    words = segment(text)
    return Counter(w for w in words if len(w) >= min_length and w.strip())


def total_count(counter: Counter) -> int:
    """Total number of word occurrences (tokens), not unique words."""
    return sum(counter.values())


def save_csv(counter: Counter, output_path: Path, min_count: int = 1) -> None:
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("word,count\n")
        for word, count in counter.most_common():
            if count >= min_count:
                f.write(f"{word},{count}\n")
