import re
from collections import Counter
from pathlib import Path

from language import Language


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
    Language.MANDARIN_TW: _segment_chinese,
    Language.MANDARIN_CN: _segment_chinese,
    Language.JAPANESE: _segment_japanese,
}


def compute(text: str, language: Language, min_length: int = 1) -> Counter:
    segment = _SEGMENTERS.get(language, _segment_generic)
    words = segment(text)
    return Counter(w for w in words if len(w) >= min_length and w.strip())


def save_csv(counter: Counter, output_path: Path, min_count: int = 1) -> None:
    output_path = Path(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("word,count\n")
        for word, count in counter.most_common():
            if count >= min_count:
                f.write(f"{word},{count}\n")
