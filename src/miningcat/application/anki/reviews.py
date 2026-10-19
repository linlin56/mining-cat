"""The user's Anki reviews in the decks of a language (Settings › Anki: the deck of its new cards, the decks synced
with its words), for the home page and the Discord status: today's state, the streak, the days with reviews
(the heatmap, a year at a time)."""
import threading
from collections import Counter
from datetime import datetime

from miningcat.application.anki.config import anki, get_config
from miningcat.domain.cards import reviews
from miningcat.domain.cards.errors import AnkiError
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect

# The first read of a deck's review log can be long (years of reviews); then only the new reviews are read.
HISTORY_TIMEOUT = 60


def language_decks(language: str) -> list[str]:
    """The decks linked to a language in Settings › Anki: the one its cards are sent to, the ones synced with its words."""
    config = get_config()
    decks = [(config["notes"].get(language) or {}).get("deck", "")]
    decks += [source["deck"] for source in config["sync"].get(language, [])]
    return [deck for deck in dict.fromkeys(decks) if deck]


class CardHistory:
    """A card's first review and the steps of its interval: (review id, interval in days) each time it got longer than
    ever, enough to tell when it reached any interval (a word is known from Settings › Anki's interval on)."""
    __slots__ = ("first", "steps")

    def __init__(self, first: int):
        self.first = first
        self.steps: list[tuple[int, int]] = []

    def add(self, review_id: int, interval: int) -> None:
        self.first = min(self.first, review_id)
        if interval > (self.steps[-1][1] if self.steps else 0):
            self.steps.append((review_id, interval))

    def copy(self) -> "CardHistory":
        history = CardHistory(self.first)
        history.steps = list(self.steps)
        return history

    def reached(self, interval: int) -> int | None:
        """The id (time in ms) of the review that gave the card that interval, or None."""
        return next((review_id for review_id, days in self.steps if days >= interval), None)


class ReviewDays:
    """The number of reviews of each Anki day, and the history of each card, per deck (subdecks apart: AnkiConnect's
    cardReviews reads one deck). Kept while MiningCat runs: a deck's review log is read once, then from its last
    review on."""

    def __init__(self):
        self._lock = threading.Lock()
        # deck -> (id of its last review read, reviews per day, {card id: its history})
        self._decks: dict[str, tuple[int, Counter, dict[int, CardHistory]]] = {}

    def _read(self, client: AnkiConnect, deck: str) -> tuple[Counter, dict[int, CardHistory]]:
        last_id, days, cards = self._decks.get(deck, (0, Counter(), {}))
        days = Counter(days)
        # [review id (ms), card id, usn, button, interval, last interval, factor, duration, type]. An interval < 0 is
        # in seconds: a learning step.
        for row in client.invoke("cardReviews", timeout=HISTORY_TIMEOUT, deck=deck, startID=last_id):
            last_id = max(last_id, row[0])
            if row[8] in reviews.REVIEW_TYPES:
                days[reviews.anki_day(datetime.fromtimestamp(row[0] / 1000))] += 1
                cards.setdefault(row[1], CardHistory(row[0])).add(row[0], max(0, int(row[4])))
        self._decks[deck] = (last_id, days, cards)
        return days, cards

    def of(self, client: AnkiConnect, decks: list[str]) -> Counter:
        total = Counter()
        with self._lock:
            for deck in decks:
                total.update(self._read(client, deck)[0])
        return total

    def cards(self, client: AnkiConnect, decks: list[str]) -> dict[int, CardHistory]:
        """The history of the cards reviewed in the decks: copies, the cache's own ones changing with the next reads."""
        result: dict[int, CardHistory] = {}
        with self._lock:
            for deck in decks:
                result.update({card: history.copy() for card, history in self._read(client, deck)[1].items()})
        return result


review_days = ReviewDays()

# AnkiConnect's cardsInfo, that many cards at a time.
CARDS_PER_REQUEST = 1000


class CardNotes:
    """The note of each card (it never changes), kept while MiningCat runs: thousands of cards are read once, most
    of them by the sync."""

    def __init__(self):
        self._lock = threading.Lock()
        self._notes: dict[int, int | None] = {}

    def remember(self, card: int, note: int) -> None:
        """A card's note, read elsewhere (the sync reads the cards of the synced decks)."""
        with self._lock:
            self._notes[card] = note

    def of(self, client: AnkiConnect, cards: list[int]) -> dict[int, int | None]:
        with self._lock:
            unknown = [card for card in cards if card not in self._notes]
            for info in client.in_batches("cardsInfo", "cards", unknown, CARDS_PER_REQUEST):
                if info.get("cardId"):
                    self._notes[info["cardId"]] = info.get("note")
            for card in unknown:
                self._notes.setdefault(card, None)  # deleted since
            return {card: self._notes[card] for card in cards}


card_notes = CardNotes()


def existing_decks(client: AnkiConnect, linked: list[str]) -> tuple[list[str], list[str]]:
    """(the linked decks and their subdecks, each read apart by cardReviews; the top ones, whose counts include their
    subdecks'), among the decks of Anki."""
    existing = client.invoke("deckNames", timeout=3)
    decks = [name for name in existing if any(reviews.in_deck(name, deck) for deck in linked)]
    return decks, reviews.top_decks([deck for deck in linked if deck in existing])


def summary(language: str, now: datetime | None = None) -> dict:
    """{linked: False} when no deck is linked to the language, {connected: False, error} when Anki doesn't answer,
    else {linked, connected, today (ISO date), reviewed, due, new, state (see domain/cards/reviews.py), streak, longest,
    days: {ISO date: reviews} of every day with reviews, for the heatmap's years}."""
    linked = language_decks(language)
    if not linked:
        return {"linked": False}
    client = anki()
    try:
        decks, top = existing_decks(client, linked)
        stats = client.invoke("getDeckStats", decks=top).values() if top else []
        by_day = review_days.of(client, decks)
    except AnkiError as exc:
        return {"linked": True, "connected": False, "error": str(exc)}
    today = reviews.anki_day(now or datetime.now())
    reviewed = by_day[today]
    due = sum(deck["review_count"] + deck["learn_count"] for deck in stats)
    current, longest = reviews.streaks(by_day, today)
    return {
        "linked": True, "connected": True, "decks": top, "today": today.isoformat(), "reviewed": reviewed, "due": due,
        "new": sum(deck["new_count"] for deck in stats), "state": reviews.today_state(reviewed, due),
        "streak": current, "longest": longest,
        "days": {day.isoformat(): count for day, count in sorted(by_day.items()) if count},
    }
