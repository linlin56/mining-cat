import re
from pathlib import Path

from miningcat.domain.cards.errors import AnkiError
from miningcat.domain.cards.fields import CARD_FIELDS

# Fixed ids so that every export uses the same note type and deck in the user's collection.
APKG_MODEL_ID = 1_740_201_100
APKG_DECK_ID = 1_740_201_200

APKG_FRONT = """<div class="word">{{Word}}</div>
{{#Sentence}}<div class="sentence">{{Sentence}}</div>{{/Sentence}}"""
APKG_BACK = """{{FrontSide}}
<hr id="answer">
<div class="reading">{{Reading}}</div>
{{Word audio}}{{Sentence audio}}
<div class="definition">{{Definition}}</div>
{{#Sentence translation}}<div class="translation">{{Sentence translation}}</div>{{/Sentence translation}}
{{Image}}
{{#Notes}}<div class="notes">{{Notes}}</div>{{/Notes}}
<div class="source">{{Source}}</div>"""

APKG_CSS = """.card { font-family: sans-serif; font-size: 20px; text-align: center; }
.word { font-size: 42px; margin: 12px 0; }
.sentence, .translation { font-size: 22px; margin: 10px 0; }
.sentence b { color: #e0583c; }
.reading { font-size: 24px; color: #666; }
.definition { text-align: left; display: inline-block; }
.notes, .source { font-size: 14px; color: #888; margin-top: 10px; }
img { max-width: 100%; }"""

APKG_FIELD_ORDER = ["word", "reading", "definition", "sentence", "sentence_translation",
                    "image", "audio", "sentence_audio", "notes", "source"]


class ApkgWriter:
    """An .apkg package of notes of MiningCat's own note type, one deck per language."""

    def __init__(self):
        try:
            import genanki
        except ImportError:
            raise AnkiError("The .apkg export needs the genanki package (pip install genanki).")
        self._genanki = genanki
        self._model = genanki.Model(
            APKG_MODEL_ID, "MiningCat",
            fields=[{"name": CARD_FIELDS[key]} for key in APKG_FIELD_ORDER],
            templates=[{"name": "Recognition", "qfmt": APKG_FRONT, "afmt": APKG_BACK}],
            css=APKG_CSS,
        )
        self._decks: dict[str, object] = {}
        self._media: set[str] = set()

    def add_note(self, deck_name: str, deck_number: int, fields: dict[str, str], identity: tuple, tags: str) -> None:
        """Adds a note to a deck (numbered so that its id stays the same from one export to the next). `fields`:
        the values of the MiningCat fields; `identity`: what tells the note apart, for its guid."""
        deck = self._decks.setdefault(deck_name, self._genanki.Deck(APKG_DECK_ID + deck_number, deck_name))
        tag_list = [re.sub(r"\s", "_", t) for t in re.split(r"[\s,]+", tags) if t]
        deck.add_note(self._genanki.Note(
            model=self._model, fields=[fields.get(key, "") for key in APKG_FIELD_ORDER],
            guid=self._genanki.guid_for("miningcat", *identity), tags=tag_list,
        ))

    def add_media(self, path: Path) -> None:
        self._media.add(str(path))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        package = self._genanki.Package(list(self._decks.values()))
        package.media_files = sorted(self._media)
        package.write_to_file(str(path))
