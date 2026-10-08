import hashlib
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from mining import db
from mining import words as words_mod
from mining.deinflect import transformer_for
from mining.languages import CHINESE_LANGUAGES, hiragana_to_katakana, is_no_space, katakana_to_hiragana, text_variants

# Longest headword tried, in characters (no-space languages) or words (other languages).
MAX_CHARS = 16
MAX_WORDS = 4
# Segmentations kept in memory (a chapter is segmented again when a dictionary changes).
CACHE_SIZE = 64

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
# Senses that make a word rare when all its senses are (Wiktionary tags).
_RARE_TAGS = frozenset(("dialect", "dialectal", "archaic", "obsolete", "rare", "dated"))
# Languages split inside words, like Japanese: Korean words carry their particles and endings.
_SPLIT_INSIDE_WORDS = {"ko"}
_PARTICLE = ""

_KANA_END = re.compile(r"[぀-ヿ]$")
# Taigi: runs of Hanji, and romanized words (Tâi-lô, POJ) with their tone marks, syllables joined by hyphens.
_HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]+")
_ROMAN_WORD = re.compile(r"[^\W\d_](?:[^\W_]|[\u0300-\u036f])*(?:-+[^\W\d_](?:[^\W_]|[\u0300-\u036f])*)*")


def taigi_reading_form(reading: str) -> str:
    """How a Taigi dictionary's reading is kept to find romanized words: lower-case Tâi-lô with tone marks,
    syllables joined by hyphens (tsia̍h-pn̄g, whether the dictionary writes chia̍h-pn̄g or tsiah8 png7)."""
    from mining.taigi import respell
    return re.sub(r"\s+", "-", respell(reading.strip().lower(), "tailo"))


@dataclass
class Lexicon:
    language: str
    signature: tuple
    # headword -> part of speech flags of its entries (for deinflection), -1 when any form is accepted
    entries: dict[str, int] = field(default_factory=dict)
    # Taigi: romanized reading (taigi_reading_form) -> headword, to read romanized text with Hanji dictionaries.
    # Japanese: kana reading -> headword, for the words usually written in kana (どこ -> 何処, だけ -> 丈). Only those,
    # when their main sense is: any reading would let kana text be read as unrelated words (した as 下 instead of
    # the past of する, はま as 浜 whose 2nd sense only is usually kana).
    readings: dict[str, str] = field(default_factory=dict)
    # headwords whose entries are all rare (negative score, as JMdict's): a split into common words is preferred
    rare: set[str] = field(default_factory=set)
    max_chars: int = 1


_lexicons: dict[str, Lexicon] = {}
_lexicon_lock = threading.Lock()
_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()


def _signature(conn, language: str) -> tuple:
    rows = conn.execute(
        "SELECT id, enabled, imported, term_count FROM dictionaries WHERE language = ? ORDER BY id", (language,),
    ).fetchall()
    return (str(db.DB_PATH),) + tuple(tuple(r) for r in rows)


# JMdict-style tags of a sense: its number first ("1 adv uk"), absent when the word has one sense ("n uk").
def _usually_kana(def_tags: str | None, score: int | None) -> bool:
    tags = (def_tags or "").split()
    if "uk" not in tags or (score or 0) < 0:
        return False
    number = next((t for t in tags if t.isdigit()), "1")
    return number == "1"


def lexicon(language: str) -> Lexicon:
    """Headwords of the enabled dictionaries of `language`, loaded once and reloaded when they change."""
    with db.session() as conn:
        signature = _signature(conn, language)
    with _lexicon_lock:
        cached = _lexicons.get(language)
        if cached is not None and cached.signature == signature:
            return cached
        transformer = transformer_for(language)
        strict = language in ("ja", "ko")
        lex = Lexicon(language, signature)
        best_score: dict[str, int] = {}
        with db.session() as conn:
            rows = conn.execute(
                "SELECT t.expression, t.reading, t.rules, t.def_tags, t.score FROM terms t JOIN dictionaries d ON d.id = t.dict_id"
                " WHERE d.enabled = 1 AND d.language = ?", (language,),
            )
            for expression, reading, rules, def_tags, score in rows:
                if not expression:
                    continue
                rules = (rules or "").split()
                if transformer is None or (not rules and not strict):
                    flags = -1
                else:
                    flags = transformer.flags_for_parts_of_speech(rules)
                score = score or 0
                if score >= 0 and _RARE_TAGS.intersection((def_tags or "").split()):
                    score = -1
                if score > best_score.get(expression, -1 << 62):
                    best_score[expression] = score
                previous = lex.entries.get(expression)
                lex.entries[expression] = -1 if previous == -1 or flags == -1 else (previous or 0) | flags
                if len(expression) > lex.max_chars:
                    lex.max_chars = min(len(expression), MAX_CHARS)
                if language == "ja" and reading and reading != expression and _usually_kana(def_tags, score):
                    lex.readings.setdefault(katakana_to_hiragana(reading), expression)
                elif language == "nan" and reading and reading != expression and re.search(r"[A-Za-z]", reading):
                    lex.readings.setdefault(taigi_reading_form(reading), expression)
        # a reading that is itself a headword stays that headword
        for reading in [r for r in lex.readings if r in lex.entries]:
            del lex.readings[reading]
        lex.rare = {expression for expression, score in best_score.items() if score < 0}
        # an inflected form is longer than its headword (食べていた, 食べる)
        if transformer is not None:
            lex.max_chars = MAX_CHARS
        _lexicons[language] = lex
        return lex


def _accepts(lex: Lexicon, headword: str, conditions: int, transformer) -> bool:
    flags = lex.entries.get(headword)
    if flags is None:
        return False
    if flags == -1 or conditions == 0 or transformer is None:
        return True
    return transformer.conditions_match(conditions, flags)


# Headword for `text`, or None: the text itself, a spelling variant, a Japanese reading, or a deinflected form.
def match(lex: Lexicon, text: str, transformer=None) -> str | None:
    variants = text_variants(text, lex.language)
    if lex.language == "ja":
        # Hiragana text isn't a katakana word (はま isn't ハマ): only the other way round (ニャー is にゃー).
        katakana = hiragana_to_katakana(text)
        variants = [v for v in variants if v == text or v != katakana]
    for variant in variants:
        if variant in lex.entries:
            return variant
        if lex.readings and variant in lex.readings:
            return lex.readings[variant]
    if transformer is None:
        return None
    # Japanese inflections always end in kana: other candidates can't be deinflected.
    if lex.language == "ja" and not _KANA_END.search(text):
        return None
    for variant in variants:
        for d in transformer.transform(variant)[1:]:
            if _accepts(lex, d.text, d.conditions, transformer):
                return d.text
            if lex.readings and d.conditions and d.text in lex.readings:
                return lex.readings[d.text]
    return None


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


def segment(language: str, text: str) -> list[tuple[int, int, str | None]]:
    """Words of `text` as (start, length, headword), headword None for a word missing from the dictionaries."""
    lex = lexicon(language)
    key = (language, lex.signature, hashlib.sha1(text.encode("utf-8")).hexdigest())
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not lex.entries:
        tokens = []
    elif language == "nan":
        tokens = _segment_taigi(text, lex)
    elif is_no_space(language) or language in _SPLIT_INSIDE_WORDS:
        tokens = _segment_no_space(text, lex, transformer_for(language))
    else:
        tokens = _segment_words(text, lex, transformer_for(language))
    with _cache_lock:
        _cache[key] = tokens
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return tokens


def statuses(language: str, headwords: list[str]) -> dict[str, dict]:
    """{headword: {"form", "status"}}: the form a word is saved under (the script the user learns), and its status."""
    preference = words_mod.chinese_script_preference(language) if language in CHINESE_LANGUAGES else None
    forms = {h: words_mod.preferred_form(language, h, preference) for h in dict.fromkeys(headwords)}
    found = words_mod.statuses_for(language, list(set(forms.values())))
    return {h: {"form": form, "status": found.get(form, "new")} for h, form in forms.items()}


def colour(language: str, text: str) -> dict:
    """Words of `text` with their status: {"words": [{headword, form, status}], "tokens": [[start, length, word index]],
    "sentences": [[start, end]]}. Words missing from the dictionaries have the index -1. The sentences are for the
    comprehension and the recommended sentences (see comprehension.py)."""
    from mining.comprehension import sentence_spans

    tokens = segment(language, text)
    headwords = list(dict.fromkeys(t[2] for t in tokens if t[2] is not None))
    index = {h: i for i, h in enumerate(headwords)}
    info = statuses(language, headwords)
    from mining.frequency import Ranker

    ranker = Ranker(language)
    return {
        "language": language,
        # rank: in the language's frequency list (None without one, or for a word it doesn't have)
        "words": [{"headword": h, **info[h], "rank": ranker.rank(h, info[h]["form"])} for h in headwords],
        # the recommended sentences only teach words ranked up to frequency["limit"] (see frequency.py)
        "frequency": ranker.frontier,
        "tokens": [[start, length, index[h] if h is not None else -1] for start, length, h in tokens],
        "sentences": [list(span) for span in sentence_spans(text)] if tokens else [],
    }


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
    with _lexicon_lock:
        _lexicons.clear()
