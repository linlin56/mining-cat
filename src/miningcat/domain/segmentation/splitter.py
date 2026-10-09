"""Splitting a text into dictionary words: the best split of runs of characters in languages written without
spaces, whole words (or expressions of a few words) in the others."""
import re

from miningcat.domain.dictionary.deinflection import LanguageTransformer
from miningcat.domain.languages import is_no_space
from miningcat.domain.segmentation.lexicon import Lexicon, match

MAX_WORDS = 4

# Characters a word can be made of: letters, marks, digits, and the Japanese long vowel / iteration marks.
_WORD_CHAR = re.compile(r"[\wー々〻ゝゞヽヾ'’\-]", re.UNICODE)

_WORD_RUN = re.compile(_WORD_CHAR.pattern + "+", re.UNICODE)

_SPACE_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)

_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# Korean particles and copula endings written after nouns (친구와, 밥을): recognised as such, never coloured.
# Wiktionary-based dictionaries don't always have them as entries.
KO_PARTICLES = frozenset(
    "은 는 이 가 을 를 의 에 에서 에게 께 께서 한테 와 과 랑 이랑 하고 도 만 까지 부터 로 으로 처럼 보다 "
    "마다 조차 밖에 이나 나 이나마 이든지 든지 요 이요 야 아 이야 이다 입니다 이에요 예요 였다 이었다".split())

# Languages split inside words, like Japanese: Korean words carry their particles and endings.
_SPLIT_INSIDE_WORDS = {"ko"}

_PARTICLE = ""

# Taigi: runs of Hanji, and romanized words (Tâi-lô, POJ) with their tone marks, syllables joined by hyphens.
_HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]+")
_ROMAN_WORD = re.compile(r"[^\W\d_](?:[^\W_]|[\u0300-\u036f])*(?:-+[^\W\d_](?:[^\W_]|[\u0300-\u036f])*)*")


# Cost of a word in the best split of a run of text: fewer words is better, rare words cost more, and a
# character no dictionary knows costs most. Chinese has no rare words in CC-CEDICT, so this is "longest words".
# A Korean particle after a word costs little: 밥을 is 밥 + 을, not a dialect verb 밥다.
def _cost(lex: Lexicon, headword: str | None) -> float:
    if headword is None:
        return 3.0
    if headword == _PARTICLE:
        return 0.3
    return 1.6 if headword in lex.rare else 1.0


# Best split of a run of word characters (dynamic programming, from the end). On equal costs the longest
# first word wins, like a greedy longest match.
def _split_run(run: str, offset: int, lex: Lexicon, transformer, memo: dict) -> list[tuple[int, int, str | None]]:
    n = len(run)
    best: list[tuple[float, int, str | None]] = [(0.0, 0, None)] * (n + 1)
    for i in range(n - 1, -1, -1):
        choice = (_cost(lex, None) + best[i + 1][0], 1, None)
        for length in range(min(lex.max_chars, n - i), 0, -1):
            piece = run[i:i + length]
            if piece not in memo:
                memo[piece] = match(lex, piece, transformer)
            options = [memo[piece]] if memo[piece] is not None else []
            if i > 0 and lex.language == "ko" and piece in KO_PARTICLES:
                options.append(_PARTICLE)
            for headword in options:
                cost = _cost(lex, headword) + best[i + length][0]
                if cost < choice[0]:
                    choice = (cost, length, headword)
        best[i] = choice
    tokens, i = [], 0
    while i < n:
        _, length, headword = best[i]
        if headword != _PARTICLE and (headword is not None or _LETTER.match(run[i])):
            tokens.append((offset + i, length, headword))
        i += length
    return tokens


# (start, length, headword or None) for every word of a text written without spaces (Chinese, Japanese).
def _segment_no_space(text: str, lex: Lexicon, transformer) -> list[tuple[int, int, str | None]]:
    tokens = []
    memo: dict[str, str | None] = {}
    for run in _WORD_RUN.finditer(text):
        tokens += _split_run(run.group(), run.start(), lex, transformer, memo)
    return tokens


# Same for languages with spaces: whole words, or a few words making a dictionary expression ("a lot of").
def _segment_words(text: str, lex: Lexicon, transformer) -> list[tuple[int, int, str | None]]:
    spans = [(m.start(), m.end()) for m in _SPACE_WORD.finditer(text) if _LETTER.search(m.group())]
    tokens = []
    k = 0
    while k < len(spans):
        start = spans[k][0]
        found = None
        for count in range(min(MAX_WORDS, len(spans) - k), 0, -1):
            end = spans[k + count - 1][1]
            # an expression never spans a line or sentence break
            if count > 1 and re.search(r"[\n.!?;:。！？]", text[start:end]):
                continue
            headword = match(lex, text[start:end], transformer)
            if headword is not None:
                found = (start, end - start, headword, count)
                break
        if found is None:
            tokens.append((start, spans[k][1] - start, None))
            k += 1
        else:
            tokens.append(found[:3])
            k += found[3]
    return tokens


# Taigi: Hanji split like Chinese, romanized words looked up whole (by their reading in Hanji dictionaries).
def _segment_taigi(text: str, lex: Lexicon) -> list[tuple[int, int, str | None]]:
    tokens = []
    memo: dict[str, str | None] = {}
    position = 0
    for run in [*_HAN_RUN.finditer(text), None]:
        end = run.start() if run else len(text)
        for word in _ROMAN_WORD.finditer(text, position, end):
            tokens.append((word.start(), len(word.group()), match(lex, word.group())))
        if run:
            tokens += _split_run(run.group(), run.start(), lex, None, memo)
            position = run.end()
    return tokens


def split_words(lex: Lexicon, text: str, transformer: LanguageTransformer | None) -> list[tuple[int, int, str | None]]:
    """Words of `text` as (start, length, headword), headword None for a word missing from the dictionaries."""
    if not lex.entries:
        return []
    if lex.language == "nan":
        return _segment_taigi(text, lex)
    if is_no_space(lex.language) or lex.language in _SPLIT_INSIDE_WORDS:
        return _segment_no_space(text, lex, transformer)
    return _segment_words(text, lex, transformer)
