import html
import re

from miningcat.application.mining import preferences, sentence_readings
from miningcat.domain.cards.fields import render_template
from miningcat.domain.sentence_readings.card_sentence import word_field
from miningcat.domain.text import taigi
from miningcat.domain.text.zhuyin import pinyin_to_zhuyin


# Fields computed from the card's: the zhuyin of a Mandarin word, from its pinyin reading (CC-CEDICT has no zhuyin),
# and the readings of the word and of the sentence's words when the card creator didn't give them (Mandarin, Taigi).
def derived_fields(language: str, fields: dict) -> dict:
    derived = {}
    if language == "zh":
        reading = re.sub(r"<[^>]+>", "", fields.get("reading", ""))
        if not fields.get("zhuyin"):
            derived["zhuyin"] = pinyin_to_zhuyin(reading)
        if not fields.get("word_readings"):
            derived["word_readings"] = word_field(re.sub(r"<[^>]+>", "", fields.get("word", "")).strip(), reading)
        if not fields.get("sentence_readings") and fields.get("sentence"):
            derived["sentence_readings"] = sentence_readings.annotate(language, fields["sentence"], reading)["field"]
    elif language == "nan":
        derived.update(_taigi_fields(fields))
    return derived


# Taigi: the reading in both romanizations (taibun's when the card has none), the readings of the word and of the
# sentence's Hanji words, in the reading system chosen in the settings.
def _taigi_fields(fields: dict) -> dict:
    word = re.sub(r"<[^>]+>", "", fields.get("word", "")).strip()
    reading = re.sub(r"<[^>]+>", "", fields.get("reading", "")).strip() or taigi.reading(word)
    system = preferences.reading_system("nan")
    derived = {}
    for key in ("tailo", "poj"):
        if not fields.get(key) and reading:
            derived[key] = taigi.respell(reading, key)
    if not fields.get("word_readings") and word:
        derived["word_readings"] = f"{word}[{taigi.respell(reading, system)}]" if reading and reading != word else word
    if not fields.get("sentence_readings") and fields.get("sentence"):
        derived["sentence_readings"] = _taigi_sentence(fields["sentence"], system)
    return derived


# The sentence's Hanji words followed by their reading, its HTML (the card's word in bold) kept around them.
def _taigi_sentence(sentence: str, system: str) -> str:
    out = []
    for part in re.split(r"(<[^>]+>)", sentence):
        if part.startswith("<"):
            out.append(part)
            continue
        for word, reading in taigi.annotate(html.unescape(part), system):
            out.append(html.escape(word, quote=False) + (f"[{reading}]" if reading else ""))
    return "".join(out)


def note_fields(setup: dict, fields: dict, media: dict, language: str = "") -> dict[str, str]:
    """The fields of the Anki note of a card, from the templates of the note setup."""
    fields = {**fields, **derived_fields(language, fields)}
    return {name: render_template(template, fields, media) for name, template in setup["fields"].items()}
