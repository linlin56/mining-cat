from miningcat.application.mining import segmentation
from miningcat.application.mining.preferences import reading_system
from miningcat.domain.segmentation.lexicon import match
from miningcat.domain.sentence_readings.card_sentence import bracketed, display_pinyin, plain_sentence
from miningcat.domain.sentence_readings.context_rules import Context, choose_reading
from miningcat.domain.sentence_readings.senses import reading_weight
from miningcat.domain.text.zhuyin import numbered_pinyin
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_queries import DictionaryQueries

# The languages whose sentences get readings.
LANGUAGES = {"zh"}


def _candidates(language: str, headwords: list[str]) -> dict[str, list[dict]]:
    """{headword: [{pinyin, weight}]}: the readings the user's dictionaries give each word, in their order,
    weight being the number of senses that make the reading likely for the word said alone."""
    found: dict[str, dict[str, dict]] = {}
    with database.session() as conn:
        for expression, reading, glossary in DictionaryQueries(conn).readings(language, headwords):
            pinyin = numbered_pinyin(reading or "")
            if not pinyin:
                continue
            candidate = found.setdefault(expression, {}).setdefault(pinyin, {"pinyin": pinyin, "weight": 0})
            candidate["weight"] += reading_weight(glossary)
    return {h: list(readings.values()) for h, readings in found.items()}


def annotate(language: str, sentence_html: str, word_reading: str = "") -> dict:
    """The words of a card's sentence with their readings: {"text", "tokens": [{start, end, text, pinyin,
    choices: [{pinyin, display}], target}], "field"}. The bold part of the sentence is the card's word, read
    `word_reading` when given. "field" is the sentence with its readings in brackets."""
    text, bold = plain_sentence(sentence_html or "")
    if language not in LANGUAGES or not text.strip():
        return {"text": text, "tokens": [], "field": ""}
    lex = segmentation.lexicon(language)
    pieces = [(0, bold[0]), bold, (bold[1], len(text))] if bold else [(0, len(text))]
    tokens: list[dict] = []
    for a, b in pieces:
        if a >= b:
            continue
        if (a, b) == bold:
            word = text[a:b].strip()
            lead = len(text[a:b]) - len(text[a:b].lstrip())
            headword = match(lex, word) or word
            tokens.append({"start": a + lead, "end": a + lead + len(word), "text": word, "headword": headword,
                           "target": True})
            continue
        for start, length, headword in segmentation.segment(language, text[a:b]):
            tokens.append({"start": a + start, "end": a + start + length, "text": text[a + start:a + start + length],
                           "headword": headword, "target": False})

    candidates = _candidates(language, [t["headword"] for t in tokens])
    system = reading_system(language)
    target_pinyin = numbered_pinyin(word_reading)
    for i, token in enumerate(tokens):
        options = candidates.get(token["headword"], [])
        if token["target"] and target_pinyin:
            token["pinyin"] = target_pinyin
            if target_pinyin not in [o["pinyin"] for o in options]:
                options = [{"pinyin": target_pinyin, "weight": 0}, *options]
        elif options:
            token["pinyin"] = choose_reading(options, token["headword"], Context(tokens, i))
        else:
            token["pinyin"] = ""
        token["choices"] = [{"pinyin": o["pinyin"], "display": display_pinyin(o["pinyin"], system)} for o in options]
        del token["headword"]
    return {"text": text, "tokens": tokens, "field": bracketed(text, tokens)}


