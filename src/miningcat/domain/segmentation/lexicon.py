import re
from dataclasses import dataclass, field

from miningcat.domain.dictionary.deinflection import LanguageTransformer
from miningcat.domain.text.kana import hiragana_to_katakana, katakana_to_hiragana
from miningcat.domain.text.variants import text_variants

# Longest headword tried, in characters (no-space languages) or words (other languages).
MAX_CHARS = 16

# Senses that make a word rare when all its senses are (Wiktionary tags).
_RARE_TAGS = frozenset(("dialect", "dialectal", "archaic", "obsolete", "rare", "dated"))

_KANA_END = re.compile(r"[぀-ヿ]$")


@dataclass
class Lexicon:
    """The headwords of the enabled dictionaries of a language, as the segmentation needs them."""

    language: str
    signature: tuple
    # headword -> part of speech flags of its entries (for deinflection), -1 when any form is accepted
    entries: dict[str, int] = field(default_factory=dict)
    # Japanese: kana reading -> headword, for the words usually written in kana (どこ -> 何処, だけ -> 丈). Only those,
    # when their main sense is: any reading would let kana text be read as unrelated words (した as 下 instead of
    # the past of する, はま as 浜 whose 2nd sense only is usually kana).
    readings: dict[str, str] = field(default_factory=dict)
    # headwords whose entries are all rare (negative score, as JMdict's): a split into common words is preferred
    rare: set[str] = field(default_factory=set)
    max_chars: int = 1


# JMdict-style tags of a sense: its number first ("1 adv uk"), absent when the word has one sense ("n uk").
def _usually_kana(def_tags: str | None, score: int | None) -> bool:
    tags = (def_tags or "").split()
    if "uk" not in tags or (score or 0) < 0:
        return False
    number = next((t for t in tags if t.isdigit()), "1")
    return number == "1"


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


def build_lexicon(language: str, signature: tuple, rows, transformer: LanguageTransformer | None) -> Lexicon:
    """The lexicon of the headwords of dictionary rows (expression, reading, rules, def_tags, score)."""
    strict = language in ("ja", "ko")
    lex = Lexicon(language, signature)
    best_score: dict[str, int] = {}
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
    # a reading that is itself a headword stays that headword
    for reading in [r for r in lex.readings if r in lex.entries]:
        del lex.readings[reading]
    lex.rare = {expression for expression, score in best_score.items() if score < 0}
    # an inflected form is longer than its headword (食べていた, 食べる)
    if transformer is not None:
        lex.max_chars = MAX_CHARS
    return lex
