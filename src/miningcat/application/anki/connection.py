from miningcat.application.anki.cards import _search_text
from miningcat.application.anki.config import anki
from miningcat.domain.cards.errors import AnkiError


def status() -> dict:
    """Whether Anki answers, and its decks and note types."""
    client = anki()
    try:
        version = client.invoke("version", timeout=3)
        decks = sorted(client.invoke("deckNames"))
        models = sorted(client.invoke("modelNames"))
        return {"connected": True, "version": version, "decks": decks, "models": models}
    except AnkiError as exc:
        return {"connected": False, "error": str(exc), "decks": [], "models": []}


def model_fields(model: str) -> list[str]:
    return anki().invoke("modelFieldNames", modelName=model)


# Notes read to find a deck's note types: a deck rarely mixes many, spread samples find them all.
DECK_SAMPLE = 200


def deck_fields(deck: str) -> list[str]:
    """The fields of the note types used in a deck, those of its most common note type first."""
    client = anki()
    note_ids = client.invoke("findNotes", query=f'"deck:{_search_text(deck)}"')
    sample = note_ids[::max(1, len(note_ids) // DECK_SAMPLE)]
    counts: dict[str, int] = {}
    for note in client.in_batches("notesInfo", "notes", sample, 100):
        counts[note["modelName"]] = counts.get(note["modelName"], 0) + 1
    fields: list[str] = []
    for model in sorted(counts, key=counts.get, reverse=True):
        fields += [f for f in client.invoke("modelFieldNames", modelName=model) if f not in fields]
    return fields
