"""The card queue: cards made in the card creator wait in the database until Anki takes them."""
import re

from miningcat.application.anki.card_media import anki_payload, card_media_dir, store_media
from miningcat.application.anki.config import anki, note_setup
from miningcat.application.anki.note_fields import note_fields
from miningcat.application.mining import words
from miningcat.domain.cards.errors import AnkiError, AnkiUnavailable, MediaUnavailable
from miningcat.domain.cards.field_text import plain_field_text
from miningcat.domain.cards.fields import CARD_FIELDS, MEDIA_FIELDS
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.persistence.card_repository import CardRepository
from miningcat.infrastructure.persistence.database import database


def create_card(language: str, fields: dict, media_input: dict, tags: str = "", send: bool = True,
                key_reading: str = "") -> dict:
    """Saves a card from the card creator, marks its word as learning, and tries to send it to Anki.
    key_reading identifies the word when the reading field shows another system (zhuyin for pinyin)."""
    if language not in LANGUAGES:
        raise AnkiError(f"Unknown language: {language}")
    clean = {key: str(fields.get(key) or "") for key in CARD_FIELDS if key not in MEDIA_FIELDS}
    expression = re.sub(r"<[^>]+>", "", clean["word"]).strip()
    if not expression:
        raise AnkiError("The card has no word.")
    reading = key_reading.strip() or re.sub(r"<[^>]+>", "", clean["reading"]).strip()
    media = {kind: store_media(kind, (media_input or {}).get(kind)) for kind in MEDIA_FIELDS}
    media = {k: v for k, v in media.items() if v}
    with database.session() as conn:
        card_id = CardRepository(conn).add(language, expression, reading, clean, media, tags.strip())
    words.set_status(language, expression, reading, "learning", source="card")
    card = get_card(card_id)
    if send:
        card = send_card(card_id)
    return card


def get_card(card_id: int) -> dict:
    with database.session() as conn:
        card = CardRepository(conn).get(card_id)
    if card is None:
        raise AnkiError("Unknown card.")
    return card


def list_cards(status: str | None = None, limit: int = 200, language: str | None = None) -> list[dict]:
    with database.session() as conn:
        return CardRepository(conn).search(status, limit, language)


def delete_card(card_id: int) -> None:
    card = get_card(card_id)
    for media in card["media"].values():
        if media:  # a link's file too, once downloaded (card_media.media_file)
            (card_media_dir() / media["filename"]).unlink(missing_ok=True)
    with database.session() as conn:
        CardRepository(conn).delete(card_id)


def set_card(card_id: int, **values) -> None:
    with database.session() as conn:
        CardRepository(conn).update(card_id, **values)


def _search_text(text: str) -> str:
    return re.sub(r'([\\"*_])', r"\\\1", text)


def _word_in_deck(client, setup: dict, expression: str) -> bool:
    """Whether the deck has a note of this word, in the note field holding the word (True when there's none)."""
    field = next((name for name, template in setup["fields"].items() if re.search(r"\{word(_readings)?\}", template)), None)
    if field is None:
        return True
    note_ids = client.invoke("findNotes", query=f'"deck:{_search_text(setup["deck"])}" "{_search_text(field)}:*{_search_text(expression)}*"')
    for note in client.in_batches("notesInfo", "notes", note_ids, 500):
        if plain_field_text(note["fields"].get(field, {}).get("value", "")) == expression:
            return True
    return False


def send_card(card_id: int) -> dict:
    """Sends one card to Anki. If Anki is closed the card stays pending; if Anki refuses it, it fails."""
    card = get_card(card_id)
    if card["status"] == "sent":
        return card
    try:
        setup = note_setup(card["language"])
    except AnkiError as exc:
        set_card(card_id, status="pending", error=str(exc))
        return get_card(card_id)
    try:
        client = anki()
        for media in card["media"].values():
            client.invoke("storeMediaFile", **anki_payload(media))
        note = {
            "deckName": setup["deck"],
            "modelName": setup["model"],
            "fields": note_fields(setup, card["fields"], card["media"], card["language"]),
            "tags": [t for t in re.split(r"[\s,]+", f"{setup.get('tags', '')} {card['tags']}") if t],
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        }
        try:
            note_id = client.invoke("addNote", note=note)
        except AnkiError as exc:
            if "duplicate" not in str(exc) or _word_in_deck(client, setup, card["expression"]):
                raise
            # Anki only compares the first field: in note types starting with the sentence (Migaku's), another
            # word's card with the same sentence isn't a duplicate of this one.
            note["options"]["allowDuplicate"] = True
            note_id = client.invoke("addNote", note=note)
    except (AnkiUnavailable, MediaUnavailable) as exc:
        set_card(card_id, status="pending", error=str(exc))
        return get_card(card_id)
    except (AnkiError, OSError) as exc:
        set_card(card_id, status="failed", error=str(exc))
        return get_card(card_id)
    set_card(card_id, status="sent", error=None, anki_note_id=note_id)
    words.set_status(card["language"], card["expression"], card["reading"], "learning",
                     source="card", anki_note_id=note_id)
    return get_card(card_id)


def send_pending(language: str | None = None) -> dict:
    sent = failed = waiting = 0
    for card in list_cards("pending", 10_000, language) + list_cards("failed", 10_000, language):
        result = send_card(card["id"])
        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "failed":
            failed += 1
        else:
            waiting += 1
            if "isn't reachable" in (result["error"] or ""):
                break  # Anki is closed: no use trying the others
    return {"sent": sent, "failed": failed, "pending": waiting}
