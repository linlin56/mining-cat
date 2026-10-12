"""The user's Anki reviews: where today's reviews stand, and the streak of days with reviews."""
from datetime import date, datetime, timedelta

NOT_STARTED = "not_started"  # cards due, none reviewed yet today
IN_PROGRESS = "in_progress"  # some reviewed, some still due
DONE = "done"                # reviewed today, nothing due any more
NOTHING_DUE = "nothing_due"  # nothing reviewed, nothing due

ONE_DAY = timedelta(days=1)
# Anki's day starts at 4 a.m. by default ("Next day starts at"), a setting AnkiConnect doesn't give.
ROLLOVER = timedelta(hours=4)
# Anki's review log types that are reviews (learning, review, relearning, filtered deck), not a manual reschedule.
REVIEW_TYPES = {0, 1, 2, 3}


def anki_day(moment: datetime) -> date:
    """The Anki day of a moment (local time): before the rollover, it's still the day before."""
    return (moment - ROLLOVER).date()


def in_deck(name: str, deck: str) -> bool:
    """Whether the deck `name` is `deck` or one of its subdecks ("Mining::Chinese" is in "Mining")."""
    return name == deck or name.startswith(deck + "::")


def top_decks(decks: list[str]) -> list[str]:
    """The decks that aren't in another one of the list: their counts already include their subdecks'."""
    return [d for d in dict.fromkeys(decks) if not any(other != d and in_deck(d, other) for other in decks)]


def today_state(reviewed: int, due: int) -> str:
    """Today's reviews: `reviewed` cards reviewed today, `due` cards still due (review and learning cards)."""
    if due:
        return IN_PROGRESS if reviewed else NOT_STARTED
    return DONE if reviewed else NOTHING_DUE


def streaks(days: dict[date, int], today: date) -> tuple[int, int]:
    """(current, longest) streak: days in a row with reviews. The current one ends today, or yesterday while today has
    no review yet: a streak is only lost once a whole day passes without reviews."""
    reviewed = {day for day, count in days.items() if count > 0}
    end = today if today in reviewed else today - ONE_DAY
    current = 0
    while end - current * ONE_DAY in reviewed:
        current += 1
    longest = run = 0
    previous = None
    for day in sorted(reviewed):
        run = run + 1 if previous is not None and day - previous == ONE_DAY else 1
        longest = max(longest, run)
        previous = day
    return current, longest
