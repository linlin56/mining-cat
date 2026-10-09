"""Taigi's Hanji (漢字), read with taibun (its dictionary is the Ministry of Education's), and romanized words written
in Hanji with the same dictionary reversed: a pronunciation may have several Hanji, the most common characters are
chosen, and a syllable without Hanji stays romanized (Hàn-lô)."""
import re
import unicodedata
from functools import lru_cache

from miningcat.domain.text.taigi.romanization import (
    HAN,
    ROMAN_WORD,
    SYSTEMS,
    Syllable,
    parse_word,
    respell,
    write_word,
)


@lru_cache(maxsize=4)
def _converter(system: str, punctuation: str = "format"):
    from taibun import Converter
    return Converter(system=system, punctuation=punctuation)


def _hanji_to_tailo(text: str, punctuation: str = "format") -> str:
    if not HAN.search(text):
        return text
    try:
        converted = _converter("Tailo", punctuation).get(text)
    except ImportError:
        raise RuntimeError("Reading Hanji needs the taibun package (pip install taibun).")
    # taibun writes an empty neutral-tone syllable for a "--" already in the text (走--矣 -> tsáu----ah)
    return re.sub(r"-{3,}", "--", converted)


def convert(text: str, target: str, numbers: bool = False) -> str:
    """The text written in `target` ('hanji', 'tailo' or 'poj'), from any of the three or a mix of them (Hàn-lô).
    numbers: tone numbers instead of tone marks, for a romanization."""
    if target not in SYSTEMS:
        raise ValueError(f"Unknown Taigi writing system: {target!r}")
    if not text:
        return text
    # line by line: taibun joins lines and reformats what isn't Hanji (subtitle timecodes...)
    if "\n" in text:
        return "\n".join(convert(line, target, numbers) for line in text.split("\n"))
    if target == "hanji":
        return to_hanji(text)
    return respell(_hanji_to_tailo(text), target, numbers)


def romanize(text: str, system: str = "tailo", numbers: bool = False) -> str:
    """Romanization of a word or a text (Hanji or another romanization), keeping the original's punctuation."""
    return respell(_hanji_to_tailo(text, "none"), system, numbers)


@lru_cache(maxsize=1)
def _hanji_index() -> tuple[dict[tuple[str, ...], str], int]:
    """{syllable keys: Hanji} from taibun's dictionary, and the longest word in syllables. A pronunciation with
    several Hanji gets the most common word: by its frequency in Chinese (jieba's dictionary: 去 rather than 氣 for
    khì), else by how many words of the dictionary have its characters."""
    from taibun import taibun as data

    counts: dict[str, int] = {}
    for word in data.word_dict:
        for char in word:
            counts[char] = counts.get(char, 0) + 1
    chinese = _chinese_frequencies()
    candidates: dict[tuple[str, ...], list[str]] = {}
    longest = 1
    for word, reading in data.word_dict.items():
        syllables = parse_word(unicodedata.normalize("NFD", reading.strip("-")))
        if not syllables or not HAN.search(word):
            continue
        key = tuple(s.key for s in syllables)
        candidates.setdefault(key, []).append(word)
        longest = max(longest, len(key))
    score = lambda word: (chinese.get(data.to_simplified(word), 0), sum(counts.get(c, 0) for c in word) / len(word))
    return {key: max(words, key=score) for key, words in candidates.items()}, longest


def _chinese_frequencies() -> dict[str, int]:
    try:
        import jieba
        jieba.setLogLevel(60)
        jieba.initialize()
        return jieba.dt.FREQ
    except Exception:  # jieba missing or its dictionary unreadable: the character counts decide
        return {}


def _word_to_hanji(syllables: list[Syllable], index: dict, longest: int) -> list[tuple[str, bool]]:
    """(text, is_hanji) pieces of a word: the longest dictionary words from the left, a syllable without Hanji as is."""
    pieces, i = [], 0
    while i < len(syllables):
        for n in range(min(longest, len(syllables) - i), 0, -1):
            key = tuple(s.key for s in syllables[i:i + n])
            hanji = index.get(key)
            if hanji is None and n == 1:
                # a neutral-tone syllable (--ah) or a tone sandhi spelling: any tone of the syllable will do
                hanji = next((index[k] for t in range(10) if (k := (f"{syllables[i].letters}{t}",)) in index), None)
            if hanji is not None:
                pieces.append((hanji, True))
                i += n
                break
        else:
            pieces.append((write_word([syllables[i]]), False))
            i += 1
    return pieces


_FULL_WIDTH = str.maketrans({",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"})


def to_hanji(text: str) -> str:
    """Romanized words of the text written in Hanji (best effort: the dictionary's most common characters).
    Hanji and other text stay as they are."""
    try:
        index, longest = _hanji_index()
    except ImportError:
        raise RuntimeError("Writing Hanji needs the taibun package (pip install taibun).")
    nfd = unicodedata.normalize("NFD", text)
    out, last = [], 0
    for m in ROMAN_WORD.finditer(nfd):
        syllables = parse_word(m.group())
        if syllables is None or any(s.upper for s in syllables):  # OK, TV: not Taigi
            continue
        out.append(nfd[last:m.start()])
        previous_hanji = None
        for piece, is_hanji in _word_to_hanji(syllables, index, longest):
            if previous_hanji is False or (previous_hanji and not is_hanji):
                out.append("-")
            out.append(piece)
            previous_hanji = is_hanji
        last = m.end()
    out.append(nfd[last:])
    result = unicodedata.normalize("NFC", "".join(out))
    # Hanji words aren't separated by spaces, and take full-width punctuation
    han = HAN.pattern
    result = re.sub(rf"(?<={han}) +(?={han})", "", result)
    result = re.sub(rf"(?<={han})[ ]*([,.!?:;]) *", lambda m: m.group(1).translate(_FULL_WIDTH), result)
    return result


def reading(hanji: str, system: str = "tailo") -> str:
    """Romanization of a Hanji word ("" when it has no Hanji or taibun isn't installed)."""
    if not HAN.search(hanji or ""):
        return ""
    try:
        return romanize(hanji, system)
    except RuntimeError:
        return ""


def _tokens(text: str) -> list[str]:
    """The text cut into taibun's words, spaces included. The tokeniser drops spaces and writes some characters
    as variants (臺 -> 台): the pieces are taken from the text itself."""
    from taibun import Tokeniser

    pieces, pos = [], 0
    for token in Tokeniser(False).tokenise(text):
        while pos < len(text) and text[pos].isspace():
            pieces.append(text[pos])
            pos += 1
        pieces.append(text[pos:pos + len(token)])
        pos += len(token)
    if pos < len(text):
        pieces.append(text[pos:])
    return pieces


def annotate(sentence: str, system: str = "tailo") -> list[tuple[str, str]]:
    """(word, reading) pairs of a sentence, reading "" for punctuation and non-Hanji text: 我欲 -> [(我, guá), (欲, beh)]."""
    try:
        tokens = _tokens(sentence)
    except ImportError:
        return [(sentence, "")] if sentence else []
    return [(token, reading(token, system) if HAN.search(token) else "") for token in tokens]


def tokenize(text: str) -> list[str]:
    """Words of a Taigi text: Hanji words (taibun's tokeniser) and romanized words."""
    text = unicodedata.normalize("NFC", text)
    try:
        tokens = _tokens(text)
    except ImportError:  # one word per character / per run of letters
        tokens = re.findall(rf"{HAN.pattern}|[^\W\d_](?:[^\W\d_]|[\u0300-\u036f-])*", text)
    return [t for t in tokens if re.search(r"[^\W\d_]", t)]
