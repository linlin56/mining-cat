import time
from pathlib import Path

from miningcat.application.anki.card_media import card_media_dir, media_file
from miningcat.application.anki.cards import get_card, list_cards, set_card
from miningcat.application.anki.config import DEFAULT_TAG
from miningcat.config.paths import paths
from miningcat.domain.cards.errors import AnkiError, MediaUnavailable
from miningcat.domain.cards.fields import CARD_FIELDS, MEDIA_FIELDS, media_markup
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.anki.apkg import ApkgWriter


def _note_values(card: dict) -> dict[str, str]:
    values = {}
    for key in CARD_FIELDS:
        if key in MEDIA_FIELDS:
            values[key] = media_markup("image" if key == "image" else "audio", card["media"].get(key))
        else:
            values[key] = card["fields"].get(key, "")
    return values


def export_apkg(card_ids: list[int] | None = None, mark_exported: bool = True) -> Path:
    """Writes the pending (or given) cards to an .apkg file with MiningCat's own note type."""
    writer = ApkgWriter()
    cards = [get_card(i) for i in card_ids] if card_ids else list_cards("pending", 10_000) + list_cards("failed", 10_000)
    if not cards:
        raise AnkiError("There are no cards to export.")
    card_media_dir().mkdir(parents=True, exist_ok=True)
    for card in cards:
        for media in card["media"].values():
            try:
                writer.add_media(media_file(media))
            except MediaUnavailable:
                continue
        language = LANGUAGES.get(card["language"], card["language"])
        writer.add_note(
            f"MiningCat::{language}", sorted(LANGUAGES).index(card["language"]), _note_values(card),
            (card["language"], card["expression"], card["reading"], card["id"]), f"{DEFAULT_TAG} {card['tags']}",
        )
    out = paths.card_exports / f"miningcat_{time.strftime('%Y-%m-%d_%H%M%S')}.apkg"
    writer.write(out)
    if mark_exported:
        for card in cards:
            set_card(card["id"], status="exported", error=None)
    return out
