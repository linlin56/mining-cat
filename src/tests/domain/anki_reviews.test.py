from datetime import date, datetime, timedelta

import pytest

from miningcat.domain.cards import reviews

TODAY = date(2026, 10, 12)


def days_before(*offsets: int, count: int = 10) -> dict[date, int]:
    return {TODAY - timedelta(days=offset): count for offset in offsets}


@pytest.mark.parametrize("reviewed, due, state", [
    (0, 30, reviews.NOT_STARTED), (12, 18, reviews.IN_PROGRESS), (30, 0, reviews.DONE), (0, 0, reviews.NOTHING_DUE),
])
def test_today_state(reviewed, due, state):
    assert reviews.today_state(reviewed, due) == state


def test_streak_ending_today():
    assert reviews.streaks(days_before(0, 1, 2), TODAY) == (3, 3)


def test_streak_kept_while_today_has_no_review_yet():
    assert reviews.streaks(days_before(1, 2), TODAY) == (2, 2)


def test_streak_lost_after_a_day_without_reviews():
    assert reviews.streaks(days_before(2, 3, 4), TODAY) == (0, 3)


def test_longest_streak_in_the_past():
    days = days_before(0, 1, 5, 6, 7, 8, 20)
    assert reviews.streaks(days, TODAY) == (2, 4)


def test_days_with_no_review_dont_count():
    days = {**days_before(0, 2), **days_before(1, count=0)}
    assert reviews.streaks(days, TODAY) == (1, 1)
    assert reviews.streaks({}, TODAY) == (0, 0)


def test_subdecks():
    assert reviews.in_deck("Mining::Chinese", "Mining") and reviews.in_deck("Mining", "Mining")
    assert not reviews.in_deck("Mining2", "Mining") and not reviews.in_deck("Mining", "Mining::Chinese")
    assert reviews.top_decks(["Mining::Chinese", "HSK", "Mining", "HSK"]) == ["HSK", "Mining"]


def test_anki_day():
    assert reviews.anki_day(datetime(2026, 10, 12, 3, 59)) == date(2026, 10, 11)
    assert reviews.anki_day(datetime(2026, 10, 12, 4, 0)) == date(2026, 10, 12)
