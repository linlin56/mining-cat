"""Words sent from an e-reader (the KOReader plugin) with their sentence. They wait in the inbox until the user opens
them like a text of the Clipboard and makes a card in the card creator."""
import time

from miningcat.application import study_language
from miningcat.application.mining import dictionaries, frequency, lookup as dictionary_lookup, words
from miningcat.domain.dictionary.glossary_html import glossary_html
from miningcat.domain.languages import LANGUAGES, language_key
from miningcat.domain.text.sentences import sentence_around
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.inbox_repository import InboxRepository

# Longer texts aren't a word and its sentence: the plugin sends a few sentences at most.
MAX_LENGTHS = {"word": 200, "sentence": 5_000, "before": 5_000, "after": 5_000, "book": 500, "location": 200, "uid": 100}


class InboxError(Exception):
    """A word the inbox can't take: shown to the plugin as is."""


def _text(values: dict, key: str) -> str:
    text = str(values.get(key) or "")
    if key == "sentence":
        text = text.strip()
    elif key not in ("before", "after"):  # their spaces and line breaks tell where the sentence ends
        text = " ".join(text.split())
    if len(text) > MAX_LENGTHS[key]:
        raise InboxError(f"The {key} is too long ({len(text)} characters, {MAX_LENGTHS[key]} at most).")
    return text


def _language(tag) -> str:
    """The book's language (ja, zh-TW, zh_CN...) when the user has a dictionary of it, else the language studied. Many
    books tell a wrong language (en, a converter's default): a language without a dictionary isn't the one studied."""
    book = language_key(str(tag or "").replace("_", "-"))
    if book in LANGUAGES and any(d["language"] == book and d["enabled"] for d in dictionaries.list_dictionaries()):
        return book
    language = study_language.current() or (book if book in LANGUAGES else None)
    if language is None:
        raise InboxError("The book has no language MiningCat knows, and no language is studied yet.")
    return language


def receive(values: dict) -> dict:
    """Adds a word sent from the e-reader: {word, sentence, language?, book?, location?, sent?, uid?}. Instead of the
    sentence, the text `before` and `after` the word: its sentence is cut from them.
    The same uid sent twice (the plugin sending again after a lost answer) is added once."""
    word = _text(values, "word")
    if not word:
        raise InboxError("The word is missing.")
    if values.get("before") or values.get("after"):
        sentence = sentence_around(_text(values, "before"), word, _text(values, "after"))
    else:
        sentence = _text(values, "sentence") or word
    sent = values.get("sent")
    sent = float(sent) if isinstance(sent, (int, float)) and not isinstance(sent, bool) and sent > 0 else time.time()
    with database.session() as conn:
        repository = InboxRepository(conn)
        item_id = repository.add(_language(values.get("language")), word, sentence, _text(values, "book"),
                                 _text(values, "location"), sent, _text(values, "uid") or None)
        return repository.get(item_id)


def list_items(language: str | None = None) -> list[dict]:
    with database.session() as conn:
        return InboxRepository(conn).search(language)


def counts() -> dict[str, int]:
    """The number of words waiting, by language."""
    with database.session() as conn:
        return InboxRepository(conn).counts()


def remove(item_id: int) -> None:
    """Once its card is made, or when the user doesn't want one."""
    with database.session() as conn:
        InboxRepository(conn).delete(item_id)


# The e-reader's popup pages through the entries: the longest matches first, a few are enough.
LOOKUP_ENTRIES = 8


def lookup(values: dict) -> dict:
    """The entries of the user's dictionaries for a word looked up on the e-reader: {word, after?, language?}. As in
    the page's popup, the text from the word onwards is looked up, longest match first: `after`, the text following
    the word in the book, lets a word longer than the e-reader's selection be found. Each entry has its definitions
    as HTML, its status, and whether it waits in the inbox already."""
    word = _text(values, "word")
    if not word:
        raise InboxError("The word is missing.")
    language = _language(values.get("language"))
    result = dictionary_lookup.lookup(language, word + _text(values, "after")[:20])
    ranker = frequency.Ranker(language)
    with database.session() as conn:
        waiting = InboxRepository(conn).words(language)
    entries = []
    for entry in result["entries"][:LOOKUP_ENTRIES]:
        entries.append({
            "expression": entry["expression"],
            "reading": words.display_reading(language, entry["expression"], entry.get("reading") or ""),
            "status": entry["status"],
            "frequency_rank": ranker.rank(entry["expression"], entry.get("form") or ""),
            "in_inbox": bool({entry["expression"], entry.get("form"), entry.get("source")} & waiting),
            "definitions": [{"dictionary": d["dictionary"], "html": glossary_html(d["glossary"])}
                            for d in entry["definitions"]],
        })
    return {"language": language, "dictionaries": result["dictionaries"], "entries": entries}
