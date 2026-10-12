"""The user's Anki reviews in the decks of a language (Settings › Anki: the deck of its new cards, the decks synced
with its words), for the home page and the Discord status: today's state, the streak, the days of the last year
(the heatmap)."""
import threading
from collections import Counter
from datetime import datetime, timedelta

from miningcat.application.anki.config import anki, get_config
from miningcat.domain.cards import reviews
from miningcat.domain.cards.errors import AnkiError
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect

# The days shown by the heatmap: 53 weeks, the current one included.
HEATMAP_DAYS = 53 * 7
# The first read of a deck's review log can be long (years of reviews); then only the new reviews are read.
HISTORY_TIMEOUT = 60


def language_decks(language: str) -> list[str]:
    """The decks linked to a language in Settings › Anki: the one its cards are sent to, the ones synced with its words."""
    config = get_config()
    decks = [(config["notes"].get(language) or {}).get("deck", "")]
    decks += [source["deck"] for source in config["sync"].get(language, [])]
    return [deck for deck in dict.fromkeys(decks) if deck]


class ReviewDays:
    """The number of reviews of each Anki day, per deck (subdecks apart: AnkiConnect's cardReviews reads one deck).
    Kept while MiningCat runs: a deck's review log is read once, then from its last review on."""

    def __init__(self):
        self._lock = threading.Lock()
        self._decks: dict[str, tuple[int, Counter]] = {}  # deck -> (id of its last review read, reviews per day)

    def of(self, client: AnkiConnect, decks: list[str]) -> Counter:
        total = Counter()
        with self._lock:
            for deck in decks:
                last_id, days = self._decks.get(deck, (0, Counter()))
                days = Counter(days)
                # [review id (ms), card id, usn, button, interval, last interval, factor, duration, type]
                for row in client.invoke("cardReviews", timeout=HISTORY_TIMEOUT, deck=deck, startID=last_id):
                    last_id = max(last_id, row[0])
                    if row[8] in reviews.REVIEW_TYPES:
                        days[reviews.anki_day(datetime.fromtimestamp(row[0] / 1000))] += 1
                self._decks[deck] = (last_id, days)
                total.update(days)
        return total


review_days = ReviewDays()


def summary(language: str, now: datetime | None = None) -> dict:
    """{linked: False} when no deck is linked to the language, {connected: False, error} when Anki doesn't answer,
    else {linked, connected, today (ISO date), reviewed, due, new, state (see domain/cards/reviews.py), streak, longest,
    days: {ISO date: reviews} of the heatmap's days}."""
    linked = language_decks(language)
    if not linked:
        return {"linked": False}
    client = anki()
    try:
        existing = client.invoke("deckNames", timeout=3)
        # The decks and their subdecks, each read apart; their due counts, from the top ones (with their subdecks').
        decks = [name for name in existing if any(reviews.in_deck(name, deck) for deck in linked)]
        top = reviews.top_decks([deck for deck in linked if deck in existing])
        stats = client.invoke("getDeckStats", decks=top).values() if top else []
        by_day = review_days.of(client, decks)
    except AnkiError as exc:
        return {"linked": True, "connected": False, "error": str(exc)}
    today = reviews.anki_day(now or datetime.now())
    reviewed = by_day[today]
    due = sum(deck["review_count"] + deck["learn_count"] for deck in stats)
    current, longest = reviews.streaks(by_day, today)
    first_day = today - timedelta(days=HEATMAP_DAYS - 1)
    return {
        "linked": True, "connected": True, "decks": top, "today": today.isoformat(), "reviewed": reviewed, "due": due,
        "new": sum(deck["new_count"] for deck in stats), "state": reviews.today_state(reviewed, due),
        "streak": current, "longest": longest,
        "days": {day.isoformat(): count for day, count in sorted(by_day.items()) if day >= first_day and count},
    }
