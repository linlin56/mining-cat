from datetime import datetime, timedelta

import pytest

import fake_ankiconnect
from miningcat.application import anki
import importlib

from miningcat.application.anki import goals, reviews
from miningcat.application.anki.config import anki as anki_client
from miningcat.application.mining import words
from miningcat.domain.words.status import WordError

NOW = datetime(2026, 10, 19, 15, 0)


def review_id(days_ago: int) -> int:
    return int((NOW - timedelta(days=days_ago)).replace(hour=12).timestamp() * 1000)


@pytest.fixture(autouse=True)
def _empty_caches(monkeypatch):
    monkeypatch.setattr(goals, "review_days", reviews.ReviewDays())
    notes = reviews.CardNotes()
    for module in (goals, reviews, importlib.import_module("miningcat.application.anki.sync")):
        monkeypatch.setattr(module, "card_notes", notes)


@pytest.fixture
def fake_anki():
    server, fake, url = fake_ankiconnect.serve()
    anki.save_config({"url": url, "notes": {"zh": {"deck": "Mining::Chinese"}},
                      "sync": {"zh": [{"deck": "Mining::Chinese", "field": "Hanzi"}]}})
    yield fake
    server.shutdown()


def add_note(fake, word: str, interval: int, new: bool = False) -> tuple[int, int]:
    note = fake.add_existing("Mining::Chinese", "Basic", {"Hanzi": word}, interval=interval)
    card = fake.notes[note]["cards"][0]
    if new:
        fake.cards[card]["queue"] = 0
    return note, card


def test_goals():
    today = NOW.date()
    words.set_status("zh", "我們", "", "known")
    first = goals.add_goal("zh", 5000, "2027-06-01", today)
    assert first == {"id": 1, "words": 5000, "by": "2027-06-01", "created": "2026-10-19", "status": "active"}
    goals.add_goal("zh", 1000, "2027-01-01", today)
    assert [g["words"] for g in goals.get_goals("zh")] == [1000, 5000] and goals.get_goals("ja") == []
    for words_goal, by in [(5000, "someday"), (-3, "2027-06-01"), (5000, "2026-10-19"), (1, "2027-06-01")]:
        with pytest.raises(WordError):
            goals.add_goal("zh", words_goal, by, today)
    goals.delete_goal("zh", 1)
    assert [g["id"] for g in goals.get_goals("zh")] == [2]


def test_no_goal():
    assert goals.summary("zh", NOW) == {"goals": []}


def test_reached_and_missed_goals_are_kept():
    words.set_status("ja", "猫", "ねこ", "known")
    goals.add_goal("ja", 2, "2026-12-01", NOW.date() - timedelta(days=30))
    goals.add_goal("ja", 50, "2026-10-01", NOW.date() - timedelta(days=60))
    goals.add_goal("ja", 100, "2027-10-01", NOW.date() - timedelta(days=60))
    words.set_status("ja", "犬", "いぬ", "known")
    summary = goals.summary("ja", NOW)
    by_words = {g["words"]: g for g in summary["goals"]}
    assert by_words[2]["status"] == "reached" and by_words[2]["reached_on"] == "2026-10-19"
    assert by_words[50]["status"] == "missed" and by_words[50]["missed_known"] == 0
    assert summary["current"]["words"] == 100 and summary["plan"]["remaining"] == 98
    assert goals.get_goals("ja")[0]["status"] == "missed"  # saved


def test_only_past_goals():
    goals.add_goal("ja", 1, "2026-10-01", NOW.date() - timedelta(days=60))
    summary = goals.summary("ja", NOW)
    assert summary["current"] is None and summary["plan"] is None and summary["goals"][0]["status"] == "missed"


def test_without_anki():
    goals.add_goal("ja", 10, "2027-01-01", NOW.date())
    words.set_status("ja", "猫", "ねこ", "known")
    words.set_status("ja", "犬", "いぬ", "learning")
    summary = goals.summary("ja", NOW)
    assert summary["anki"] == {"linked": False, "connected": False}
    assert summary["history"][-1] == ["2026-10-19", 1]
    plan = summary["plan"]
    assert plan["remaining"] == 9 and plan["mine_per_day"] is None and plan["backlog"] is None


def test_anki_closed():
    anki.save_config({"url": "http://127.0.0.1:9", "notes": {"zh": {"deck": "Mining::Chinese"}}})
    goals.add_goal("zh", 10, "2027-01-01", NOW.date())
    summary = goals.summary("zh", NOW)
    assert summary["anki"]["linked"] is True and summary["anki"]["connected"] is False and summary["anki"]["error"]


def test_with_anki(fake_anki):
    goals.add_goal("zh", 100, "2027-04-01", NOW.date() - timedelta(days=60))
    known_note, known_card = add_note(fake_anki, "我們", 40)
    learning_note, learning_card = add_note(fake_anki, "天氣", 3)
    add_note(fake_anki, "朋友", 0, new=True)
    add_note(fake_anki, "電腦", 0, new=True)
    fake_anki.new_per_day["Mining::Chinese"] = 15
    fake_anki.revlog = [
        (review_id(50), "Mining::Chinese", 0, known_card, -600),  # first seen 50 days ago, a learning step
        (review_id(30), "Mining::Chinese", 1, known_card, 25),    # known 30 days ago
        (review_id(5), "Mining::Chinese", 1, known_card, 60),
        (review_id(3), "Mining::Chinese", 0, learning_card, 3),
    ]
    anki.sync()
    words.set_status("zh", "你好", "", "known")  # by hand, today
    summary = goals.summary("zh", NOW)
    assert summary["anki"] == {"linked": True, "connected": True, "decks": ["Mining::Chinese"]}
    history = dict(summary["history"])
    assert min(history) == "2026-09-19" and history["2026-09-19"] == 1 and history["2026-10-19"] == 2
    plan = summary["plan"]
    assert (plan["backlog"], plan["deck_new_per_day"], plan["remaining"]) == (2, 15, 98)
    assert plan["lag"] == 35 and plan["mine_per_day"] > 0  # too few cards: the usual lag
    assert plan["pace"] == round(1 / 30, 2)


def test_goals_are_not_settled_while_anki_is_closed():
    anki.save_config({"url": "http://127.0.0.1:9", "notes": {"zh": {"deck": "Mining::Chinese"}}})
    goals.add_goal("zh", 10, "2026-10-01", NOW.date() - timedelta(days=60))
    summary = goals.summary("zh", NOW)
    assert summary["goals"][0]["status"] == "active" and summary["current"]["words"] == 10


def test_new_cards_a_day_of_subdecks(fake_anki):
    goals.add_goal("zh", 100, "2027-04-01", NOW.date())
    fake_anki.decks["Mining::Chinese::Grammar"] = 9
    for deck in ("Mining::Chinese::Grammar", "Mining::Chinese::Grammar"):
        note = fake_anki.add_existing(deck, "Basic", {"Hanzi": "了"})
        fake_anki.cards[fake_anki.notes[note]["cards"][0]]["queue"] = 0
    fake_anki.new_per_day.update({"Mining::Chinese": 50, "Mining::Chinese::Grammar": 15})
    plan = goals.summary("zh", NOW)["plan"]
    # only the subdeck holds new cards: its limit, not the top deck's
    assert (plan["backlog"], plan["deck_new_per_day"]) == (2, 15)
    fake_anki.new_per_day["Mining::Chinese"] = 10
    assert goals.summary("zh", NOW)["plan"]["deck_new_per_day"] == 10  # the top deck's limit caps them


def test_the_last_plan_is_kept(fake_anki):
    goals.add_goal("zh", 100, "2027-04-01", NOW.date())
    first = goals.summary("zh", NOW)
    add_note(fake_anki, "我們", 40)
    anki.sync()
    assert goals.cached_summary("zh") == first  # at once: Anki isn't read
    goals.add_goal("zh", 200, "2027-08-01", NOW.date())
    assert len(goals.cached_summary("zh")["goals"]) == 2  # goals changed: a new plan


def test_the_sync_tells_the_notes_of_the_cards(fake_anki):
    note, card = add_note(fake_anki, "我們", 40)
    anki.sync()
    fake_anki.cards.clear()  # cardsInfo can't tell it any more
    assert reviews.card_notes.of(anki_client(), [card]) == {card: note}
