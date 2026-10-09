from miningcat.application.anki.config import anki
from miningcat.application.mining import preferences
from miningcat.domain.languages import LANGUAGES

def deck_name(language: str) -> str:
    """The name of MiningCat's deck of a language: "Mandarin (traditional) - MiningCat", "Japanese - MiningCat"."""
    name = LANGUAGES[language]
    script = preferences.chinese_script_preference(language) if language == "zh" else ""
    if script in ("traditional", "simplified"):
        name += f" ({script})"  # "both": the language alone
    return f"{name} - MiningCat"


def create_deck(language: str) -> dict:
    """Creates MiningCat's deck of a language in Anki (nothing changes when it's already there)."""
    name = deck_name(language)
    anki().invoke("createDeck", deck=name)
    return {"deck": name}
