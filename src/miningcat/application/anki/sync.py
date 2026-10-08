import time

from miningcat.application.anki.cards import send_pending
from miningcat.application.anki.config import anki, get_config
from miningcat.application.mining import words
from miningcat.domain.cards.field_text import plain_field_text
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.persistence.word_repository import WordRepository

# AnkiConnect requests are made on that many notes or cards at a time.
NOTES_PER_REQUEST = 500
CARDS_PER_REQUEST = 1000


class AnkiSync:
    """Sends the cards waiting for Anki, then updates word statuses from the intervals of the user's Anki cards:
    the cards of the decks chosen in the settings, and the cards sent from MiningCat."""

    def __init__(self, client: AnkiConnect, config: dict):
        self.client = client
        self.config = config
        self.known_interval = config["known_interval"]

    def run(self) -> dict:
        self.client.invoke("version", timeout=3)  # raises AnkiUnavailable when Anki is closed
        report = {"cards": send_pending(), "languages": {}}
        for language, sources in self.config["sync"].items():
            if sources:
                report["languages"][language] = self._sync_decks(language, sources)
        self._sync_sent_cards()
        settings.set("anki_last_sync", time.time())
        return report

    def _intervals(self, card_ids: list[int], skip_suspended: bool) -> dict[int, int]:
        """{note id: longest interval of its cards}"""
        intervals: dict[int, int] = {}
        for info in self.client.in_batches("cardsInfo", "cards", card_ids, CARDS_PER_REQUEST):
            if skip_suspended and info.get("queue") == -1:
                continue
            intervals[info["note"]] = max(intervals.get(info["note"], 0), int(info.get("interval") or 0))
        return intervals

    def _sync_decks(self, language: str, sources: list[dict]) -> dict:
        """The words of the notes of some decks: {deck, field holding the word, field holding its reading}."""
        updated = {"learning": 0, "known": 0, "kept": 0, "notes": 0}
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
                    status = words.apply_anki_state(
                        language, expression, reading, note["noteId"], intervals.get(note["noteId"], 0), self.known_interval)
                    updated[status if status in ("learning", "known") else "kept"] += 1
        return updated

    def _sync_sent_cards(self) -> None:
        """The words of the cards sent from MiningCat, whatever their deck."""
        with database.session() as conn:
            rows = WordRepository(conn).sent_card_words()
        if not rows:
            return
        note_ids = [r["anki_note_id"] for r in rows]
        intervals: dict[int, int] = {}
        for start in range(0, len(note_ids), NOTES_PER_REQUEST):
            card_ids = self.client.invoke(
                "findCards", query="nid:" + ",".join(str(n) for n in note_ids[start:start + NOTES_PER_REQUEST]))
            intervals.update(self._intervals(card_ids, skip_suspended=False))
        for r in rows:
            if r["anki_note_id"] in intervals:
                words.apply_anki_state(r["language"], r["expression"], r["reading"], r["anki_note_id"],
                                       intervals[r["anki_note_id"]], self.known_interval)


def sync() -> dict:
    """Sends the cards waiting for Anki, then updates word statuses from the user's Anki cards."""
    return AnkiSync(anki(), get_config()).run()
