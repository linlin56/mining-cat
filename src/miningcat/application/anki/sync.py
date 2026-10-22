import threading
import time
import uuid
from datetime import datetime

from miningcat.application.anki.cards import send_pending
from miningcat.application.anki.config import anki, get_config
from miningcat.application.anki.reviews import CARDS_PER_REQUEST, card_notes
from miningcat.application.mining import words
from miningcat.domain.cards.field_text import plain_field_text
from miningcat.domain.cards.errors import AnkiError
from miningcat.domain.cards.reviews import anki_day
from miningcat.domain.text.readings import normalize_reading
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.persistence.word_repository import WordRepository

# AnkiConnect requests are made on that many notes at a time (cards: CARDS_PER_REQUEST).
NOTES_PER_REQUEST = 500


# The words whose Anki note was deleted, their status removed by a sync: the home page asks which ones the user knows.
DELETED_SETTING = "anki_deleted_words"
# The Anki profile of the last sync: in another one, the notes aren't deleted, they just aren't there.
PROFILE_SETTING = "anki_profile"
# The home page syncs when it opens, unless a sync was made that recently (seconds).
AUTO_SYNC_EVERY = 30

# One sync at a time (the home page's, the settings'), and the deleted words changed by one thing at a time.
_lock = threading.Lock()


def _nid_queries(note_ids: list[int]):
    """Anki searches for the notes (or their cards) of some ids, NOTES_PER_REQUEST ids at a time."""
    for start in range(0, len(note_ids), NOTES_PER_REQUEST):
        yield "nid:" + ",".join(str(n) for n in note_ids[start:start + NOTES_PER_REQUEST])


class AnkiSync:
    """Sends the cards waiting for Anki (unless told not to), then updates word statuses from the intervals of the
    user's Anki cards: the cards of the decks chosen in the settings, and the cards sent from MiningCat. Anki is the
    reference: a word whose note was deleted loses its status, unless the user set it by hand."""

    def __init__(self, client: AnkiConnect, config: dict):
        self.client = client
        self.config = config
        self.known_interval = config["known_interval"]

    def run(self, send_cards: bool = True) -> dict:
        self.client.invoke("version", timeout=3)  # raises AnkiUnavailable when Anki is closed
        report = {"cards": send_pending() if send_cards else None, "languages": {}}
        for language, sources in self.config["sync"].items():
            if sources:
                report["languages"][language] = self._sync_decks(language, sources)
        self._sync_sent_cards()
        report["deleted"] = self._forget_deleted_notes()
        today = anki_day(datetime.now())
        for language in words.counts():
            words.record_known(language, today)
        settings.set("anki_last_sync", time.time())
        return report

    def _intervals(self, card_ids: list[int], skip_suspended: bool) -> dict[int, int]:
        """{note id: longest interval of its cards}"""
        intervals: dict[int, int] = {}
        for info in self.client.in_batches("cardsInfo", "cards", card_ids, CARDS_PER_REQUEST):
            if info.get("cardId"):
                card_notes.remember(info["cardId"], info["note"])
            if skip_suspended and info.get("queue") == -1:
                continue
            intervals[info["note"]] = max(intervals.get(info["note"], 0), int(info.get("interval") or 0))
        return intervals

    def _sync_decks(self, language: str, sources: list[dict]) -> dict:
        """The words of the notes of some decks: {deck, field holding the word, field holding its reading}. A word with
        several notes takes the longest interval of them all (whatever their order); it is counted once."""
        updated = {"learning": 0, "known": 0, "kept": 0, "notes": 0}
        # {(expression, reading): (note id, interval)}: the note of each word with the longest interval
        longest: dict[tuple[str, str], tuple[int, int]] = {}
        for source in sources:
            note_ids = self.client.invoke("findNotes", query=f'"deck:{source["deck"]}"')
            for start in range(0, len(note_ids), NOTES_PER_REQUEST):
                notes = self.client.invoke("notesInfo", notes=note_ids[start:start + NOTES_PER_REQUEST])
                intervals = self._intervals([c for n in notes for c in n.get("cards", [])], skip_suspended=True)
                for note in notes:
                    fields = note.get("fields", {})
                    expression = plain_field_text(fields.get(source["field"], {}).get("value", ""))
                    if not expression:
                        continue
                    reading = plain_field_text(fields.get(source["reading_field"], {}).get("value", "")) if source["reading_field"] else ""
                    updated["notes"] += 1
                    key, interval = (expression, normalize_reading(reading, language)), intervals.get(note["noteId"], 0)
                    if key not in longest or interval > longest[key][1]:
                        longest[key] = (note["noteId"], interval)
        for (expression, reading), (note_id, interval) in longest.items():
            status = words.apply_anki_state(language, expression, reading, note_id, interval, self.known_interval)
            updated[status if status in ("learning", "known") else "kept"] += 1
        return updated

    def _sync_sent_cards(self) -> None:
        """The words of the cards sent from MiningCat, whatever their deck."""
        with database.session() as conn:
            rows = WordRepository(conn).sent_card_words()
        if not rows:
            return
        intervals: dict[int, int] = {}
        for query in _nid_queries([r["anki_note_id"] for r in rows]):
            intervals.update(self._intervals(self.client.invoke("findCards", query=query), skip_suspended=False))
        for r in rows:
            if r["anki_note_id"] in intervals:
                words.apply_anki_state(r["language"], r["expression"], r["reading"], r["anki_note_id"],
                                       intervals[r["anki_note_id"]], self.known_interval)

    def _profile(self) -> str | None:
        """The Anki profile open, or None with an AnkiConnect too old to tell."""
        try:
            return self.client.invoke("getActiveProfile")
        except AnkiError:
            return None

    def _forget_deleted_notes(self) -> int:
        """Removes the status of the words whose Anki note doesn't exist any more (not the ones set by hand), and keeps
        them for the home page's question. Nothing is removed when another Anki profile is open than at the last sync
        (or, when AnkiConnect can't tell the profile, when Anki has none of the notes)."""
        profile, last_profile = self._profile(), settings.get(PROFILE_SETTING)
        if profile is not None:
            settings.set(PROFILE_SETTING, profile)
        with database.session() as conn:
            linked = WordRepository(conn).anki_linked_words()
        existing: set[int] = set()
        for query in _nid_queries(list({w["anki_note_id"] for w in linked})):
            existing.update(self.client.invoke("findNotes", query=query))
        same_profile = profile is not None and last_profile in (None, profile) and (last_profile or existing)
        if not (same_profile or (profile is None and existing)):
            return 0
        deleted = [w for w in linked if w["anki_note_id"] not in existing]
        if not deleted:
            return 0
        with database.session() as conn:
            repository = WordRepository(conn)
            for word in deleted:
                repository.delete(word["id"])
        waiting = settings.get(DELETED_SETTING, []) or []
        known = {(w["language"], w["expression"], w["reading"]) for w in waiting}
        # their own id: a word's row id is used again once the row is deleted
        settings.set(DELETED_SETTING, waiting + [
            {"id": uuid.uuid4().hex, "language": w["language"], "expression": w["expression"], "reading": w["reading"],
             "status": w["status"]} for w in deleted if (w["language"], w["expression"], w["reading"]) not in known])
        return len(deleted)


def sync(send_cards: bool = True) -> dict:
    """Sends the cards waiting for Anki (unless `send_cards` is False), then updates word statuses from the user's
    Anki cards. Waits for a sync already running."""
    with _lock:
        return AnkiSync(anki(), get_config()).run(send_cards)


def auto_sync() -> dict:
    """The home page's sync: the word statuses only (the cards waiting for Anki stay waiting until the user sends
    them), and not when a sync is running or was just made: {"skipped": True}."""
    if time.time() - (settings.get("anki_last_sync") or 0) < AUTO_SYNC_EVERY or not _lock.acquire(blocking=False):
        return {"skipped": True}
    try:
        return AnkiSync(anki(), get_config()).run(send_cards=False)
    finally:
        _lock.release()


def deleted_words(language: str | None = None) -> list[dict]:
    """The words (of a language) whose Anki note was deleted since the user last answered: they lost their status."""
    waiting = settings.get(DELETED_SETTING, []) or []
    return [w for w in waiting if language is None or w["language"] == language]


def settle_deleted_words(language: str, shown_ids: list[str], known_ids: list[str]) -> None:
    """The user's answer for a language, on the words shown (`shown_ids`): the ones of `known_ids` are marked known
    (by hand), the others keep no status. Words deleted since the question was asked stay for the next one."""
    with _lock:
        answered = {w["id"] for w in deleted_words(language)} & set(shown_ids)
        known = set(known_ids) & answered
        for word in deleted_words(language):
            if word["id"] in known:
                words.set_status(word["language"], word["expression"], word["reading"], "known")
        settings.set(DELETED_SETTING, [w for w in deleted_words() if w["language"] != language or w["id"] not in answered])
