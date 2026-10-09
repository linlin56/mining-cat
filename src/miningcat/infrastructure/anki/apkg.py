import re
from pathlib import Path

from miningcat.domain.cards import note_type
from miningcat.domain.cards.errors import AnkiError

# Fixed ids so that every export uses the same note type and deck in the user's collection.
APKG_MODEL_ID = 1_740_201_100
APKG_DECK_ID = 1_740_201_200


class ApkgWriter:
    """An .apkg package of notes of MiningCat's own note type, one deck per language. `templates`: its front, back
    and CSS (note_type.templates)."""

    def __init__(self, templates: dict[str, str]):
        try:
            import genanki
        except ImportError:
            raise AnkiError("The .apkg export needs the genanki package (pip install genanki).")
        self._genanki = genanki
        self._model = genanki.Model(
            APKG_MODEL_ID, note_type.NAME,
            fields=[{"name": name} for name in note_type.FIELDS],
            templates=[{"name": note_type.TEMPLATE_NAME, "qfmt": templates["front"], "afmt": templates["back"]}],
            css=templates["css"],
        )
        self._decks: dict[str, object] = {}
        self._media: set[str] = set()

    def add_note(self, deck_name: str, deck_number: int, fields: dict[str, str], identity: tuple, tags: str) -> None:
        """Adds a note to a deck (numbered so that its id stays the same from one export to the next). `fields`:
        the values of the note type's fields, by name; `identity`: what tells the note apart, for its guid."""
        deck = self._decks.setdefault(deck_name, self._genanki.Deck(APKG_DECK_ID + deck_number, deck_name))
        tag_list = [re.sub(r"\s", "_", t) for t in re.split(r"[\s,]+", tags) if t]
        deck.add_note(self._genanki.Note(
            model=self._model, fields=[fields.get(name, "") for name in note_type.FIELDS],
            guid=self._genanki.guid_for("miningcat", *identity), tags=tag_list,
        ))

    def add_media(self, path: Path) -> None:
        self._media.add(str(path))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        package = self._genanki.Package(list(self._decks.values()))
        package.media_files = sorted(self._media)
        package.write_to_file(str(path))
