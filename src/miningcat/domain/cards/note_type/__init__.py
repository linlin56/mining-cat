"""MiningCat's own Anki note type, for the users who have none: one card per note (the sentence, or the word when
there's none, on the front), for any language, the readings written in brackets after their words (字[zi4],
日本[にほん], word[wɜːd]) shown above them. Its templates are the files next to this module."""
import json
from pathlib import Path

_DIR = Path(__file__).parent

NAME = "MiningCat"
TEMPLATE_NAME = "Recognition"
FIELDS = ["Word", "Reading", "Word with reading", "Sentence", "Sentence translation", "Definition", "Word audio",
          "Sentence audio", "Image", "Notes", "Source", "Language"]

# The languages whose cards get their readings in brackets (application.anki.note_fields.derived_fields).
_BRACKET_LANGUAGES = ("zh", "nan")


def field_templates(language: str) -> dict[str, str]:
    """What each field of the note type receives for the cards of a language."""
    brackets = language in _BRACKET_LANGUAGES
    return {
        "Word": "{word}",
        "Reading": "{reading}",
        "Word with reading": "{word_readings}" if brackets else "",
        "Sentence": "{sentence_readings}" if brackets else "{sentence}",
        "Sentence translation": "{sentence_translation}",
        "Definition": "{definition}",
        "Word audio": "{audio}",
        "Sentence audio": "{sentence_audio}",
        "Image": "{image}",
        "Notes": "{notes}",
        "Source": "{source}",
        "Language": "{language}",
    }


def is_note_type(field_names: list[str]) -> bool:
    """Whether a note type has the fields of MiningCat's."""
    return set(FIELDS) <= set(field_names)


def templates(reading_systems: dict[str, str]) -> dict[str, str]:
    """The front, back and CSS of the note type. `reading_systems`: how Mandarin readings are shown, {"zh": "pinyin"
    or "zhuyin"}, written in the templates (a change of setting needs the note type updated)."""
    options = json.dumps({"readings": reading_systems, "toneColors": True}, ensure_ascii=False)
    script = "<script>\n" + (_DIR / "readings.js").read_text(encoding="utf-8").replace("__OPTIONS__", options) + "</script>"
    return {
        "front": (_DIR / "front.html").read_text(encoding="utf-8") + script,
        "back": (_DIR / "back.html").read_text(encoding="utf-8") + script,
        "css": (_DIR / "style.css").read_text(encoding="utf-8"),
    }
