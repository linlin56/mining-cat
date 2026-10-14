from datetime import datetime, timedelta

import pytest

import fake_ankiconnect
from miningcat.application import anki
from miningcat.application.anki import reviews

NOW = datetime(2026, 10, 12, 15, 0)


def review_id(days_ago: int, hour: int = 12) -> int:
    """The id of a review made `days_ago` days before NOW at `hour` (local time): its time in ms."""
    moment = (NOW - timedelta(days=days_ago)).replace(hour=hour)
    return int(moment.timestamp() * 1000)


@pytest.fixture(autouse=True)
def _empty_cache(monkeypatch):
    monkeypatch.setattr(reviews, "review_days", reviews.ReviewDays())


@pytest.fixture
def fake_anki():
    server, fake, url = fake_ankiconnect.serve()
    fake.decks.update({"Maths": 4, "Mining::Chinese::Grammar": 5})
    anki.save_config({"url": url, "notes": {"zh": {"deck": "Mining::Chinese"}},
                      "sync": {"zh": [{"deck": "Mining::Chinese", "field": "Hanzi"}]}})
    yield fake
    server.shutdown()


def test_no_deck_linked():
    assert reviews.summary("ja", NOW) == {"linked": False}


def test_anki_closed():
    anki.save_config({"url": "http://127.0.0.1:9", "notes": {"zh": {"deck": "Mining::Chinese"}}})  # nothing listens there
    summary = reviews.summary("zh", NOW)
    assert summary["connected"] is False and "isn't reachable" in summary["error"]


def test_language_decks():
    anki.save_config({"notes": {"zh": {"deck": "Mining::Chinese"}},
                      "sync": {"zh": [{"deck": "Mining::Chinese", "field": "Hanzi"}, {"deck": "HSK", "field": "Word"}]}})
    assert reviews.language_decks("zh") == ["Mining::Chinese", "HSK"]
    assert reviews.language_decks("ja") == []


def test_only_the_decks_of_the_language_count(fake_anki):
    fake_anki.revlog = [
        (review_id(0), "Mining::Chinese", 1), (review_id(0, hour=9), "Mining::Chinese::Grammar", 1),  # today
        (review_id(1), "Mining::Chinese", 1), (review_id(2), "Mining::Chinese", 0),
        (review_id(0), "Maths", 1), (review_id(5), "Maths", 1),  # not linked to Mandarin
        (review_id(3), "Mining::Chinese", 4),  # a manual reschedule, not a review
        (review_id(400), "Mining::Chinese", 1),  # more than a year ago: in the longest streak and the heatmap of 2025
    ]
    fake_anki.deck_stats = {"Mining::Chinese": {"review_count": 10, "learn_count": 2, "new_count": 5},
                            "Maths": {"review_count": 24}}
    summary = reviews.summary("zh", NOW)
    assert summary["connected"] is True and summary["decks"] == ["Mining::Chinese"]
    assert (summary["today"], summary["reviewed"], summary["due"], summary["new"]) == ("2026-10-12", 2, 12, 5)
    assert summary["state"] == "in_progress"
    assert (summary["streak"], summary["longest"]) == (3, 3)
    assert summary["days"] == {"2025-09-07": 1, "2026-10-10": 1, "2026-10-11": 1, "2026-10-12": 2}


def test_reviews_not_started(fake_anki):
    fake_anki.revlog = [(review_id(1), "Mining::Chinese", 1)]
    fake_anki.deck_stats = {"Mining::Chinese": {"review_count": 30}}
    summary = reviews.summary("zh", NOW)
    assert summary["state"] == "not_started" and summary["due"] == 30
    assert summary["streak"] == 1  # yesterday's: kept until today ends


def test_reviews_before_the_rollover_count_for_the_day_before(fake_anki):
    fake_anki.revlog = [(review_id(0, hour=2), "Mining::Chinese", 1)]  # 2 a.m.: still yesterday for Anki
    summary = reviews.summary("zh", NOW)
    assert summary["reviewed"] == 0 and summary["days"] == {"2026-10-11": 1}


def test_only_new_reviews_are_read_again(fake_anki):
    fake_anki.revlog = [(review_id(1), "Mining::Chinese", 1)]
    reviews.summary("zh", NOW)
    fake_anki.revlog.append((review_id(0), "Mining::Chinese", 1))
    fake_anki.review_reads.clear()
    summary = reviews.summary("zh", NOW)
    assert ("Mining::Chinese", review_id(1)) in fake_anki.review_reads
    assert summary["days"] == {"2026-10-11": 1, "2026-10-12": 1}
