import re

from miningcat.application.mining import sentence_readings
from miningcat.domain.cards.fields import render_template
from miningcat.domain.sentence_readings.card_sentence import word_field
from miningcat.domain.text.zhuyin import pinyin_to_zhuyin


# Fields computed from the card's: the zhuyin of a Mandarin word, from its pinyin reading (CC-CEDICT has no zhuyin),
# and the readings of the word and of the sentence's words when the card creator didn't give them.
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
    return derived


def note_fields(setup: dict, fields: dict, media: dict, language: str = "") -> dict[str, str]:
    """The fields of the Anki note of a card, from the templates of the note setup."""
    fields = {**fields, **derived_fields(language, fields)}
    return {name: render_template(template, fields, media) for name, template in setup["fields"].items()}
