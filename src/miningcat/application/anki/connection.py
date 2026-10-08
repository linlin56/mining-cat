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
