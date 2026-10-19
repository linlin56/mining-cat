from datetime import date, timedelta

from miningcat.domain.words import goals
from miningcat.domain.words.goals import Goal, Pipeline

TODAY = date(2026, 10, 19)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_maturity_uses_defaults_with_few_cards():
    assert goals.maturity({1: days_ago(100)}, {1: days_ago(60)}, TODAY) == (goals.DEFAULT_LAG, goals.DEFAULT_SUCCESS, 1)


def test_maturity_from_the_cards():
    # 40 cards first seen 200 days ago, 30 of them known 50 days later
    first_seen = {card: days_ago(200) for card in range(40)}
    matured = {card: days_ago(150) for card in range(30)}
    # cards seen too recently to tell whether they'll be known: not in the success rate
    first_seen.update({card: days_ago(10) for card in range(100, 150)})
    assert goals.maturity(first_seen, matured, TODAY) == (50, 0.75, 30)


def test_known_curve_counts_the_words():
    curve = goals.known_curve([days_ago(3), days_ago(3), days_ago(1)], {}, TODAY)
    assert list(curve.values()) == [2, 2, 3, 3] and min(curve) == days_ago(3) and max(curve) == TODAY


def test_known_curve_goes_through_the_records():
    # 10 words known today, from 10 days ago on; 30 known 6 days ago (20 forgotten since), 12 today
    dates = [days_ago(n) for n in range(10)]
    curve = goals.known_curve(dates, {days_ago(6): 30, days_ago(2): 14, TODAY: 12}, TODAY)
    assert curve[days_ago(6)] == 30 and curve[days_ago(2)] == 14 and curve[TODAY] == 12
    assert curve[days_ago(9)] == 8 and curve[days_ago(8)] == 15  # the dates' shape, scaled to reach 30
    assert [curve[days_ago(n)] for n in (5, 4, 3)] == [26, 22, 18]  # straight from 30 to 14
    # after the last record, the dates from it on
    assert goals.known_curve(dates, {days_ago(2): 20}, TODAY)[TODAY] == 22


def test_known_curve_without_any_word():
    assert goals.known_curve([], {}, TODAY) == {TODAY: 0}


def test_pace():
    curve = {days_ago(n): 1000 - 10 * n for n in range(60)}
    assert goals.pace(curve, TODAY) == 10
    young = {days_ago(n): 100 - 5 * n for n in range(5)}
    assert goals.pace(young, TODAY) == 5
    assert goals.pace({TODAY: 3}, TODAY) == 0


def test_plan():
    pipeline = Pipeline(known=1000, learning=200, backlog=300, new_per_day=20, lag=30, success=0.8)
    plan = goals.plan(Goal(3000, TODAY + timedelta(days=130)), pipeline, 10.0, TODAY)
    assert plan["remaining"] == 2000 and plan["eta"] == TODAY + timedelta(days=200)
    assert plan["needed_pace"] == round(2000 / 130, 2)
    # 0.8 x 200 learning words become known: 1840 to come from new cards, 2300 cards, over 130 - 30 days
    assert plan["cards_needed"] == 2300 and plan["new_per_day"] == 23 and plan["mine_per_day"] == 20
    assert plan["raise_limit"] is True and plan["backlog_days"] == 15
    assert plan["deck_eta"] == TODAY + timedelta(days=30 + 115)


def test_plan_with_enough_cards_waiting():
    pipeline = Pipeline(known=100, learning=0, backlog=1000, new_per_day=20, lag=30, success=1.0)
    plan = goals.plan(Goal(500, TODAY + timedelta(days=100)), pipeline, 0.0, TODAY)
    assert plan["eta"] is None and plan["mine_per_day"] == 0 and plan["new_per_day"] == 6 and not plan["raise_limit"]


def test_plan_too_late():
    pipeline = Pipeline(known=100, learning=0, lag=30)
    plan = goals.plan(Goal(500, TODAY + timedelta(days=20)), pipeline, 5.0, TODAY)
    assert plan["too_late"] is True and plan["new_per_day"] is None
    assert plan["mine_per_day"] is None and plan["backlog_days"] is None  # without Anki


def test_plan_reached():
    plan = goals.plan(Goal(500, TODAY + timedelta(days=20)), Pipeline(known=600, learning=0), 5.0, TODAY)
    assert plan["reached"] is True and plan["remaining"] == 0 and plan["cards_needed"] is None


def goal(words: int, by: date, created: date = days_ago(60), **settled) -> dict:
    return {"id": 1, "words": words, "by": by.isoformat(), "created": created.isoformat(), **settled}


def test_settle_reached():
    curve = {days_ago(n): 100 - n for n in range(20)}  # 81 known 19 days ago, 100 today
    settled = goals.settle(goal(90, TODAY + timedelta(days=10)), curve, TODAY)
    assert settled["reached_on"] == days_ago(10).isoformat() and goals.status(settled) == goals.REACHED
    # reached once: it stays so
    assert goals.settle(settled, {TODAY: 0}, TODAY) == settled


def test_settle_missed():
    curve = {days_ago(n): 100 - n for n in range(20)}
    settled = goals.settle(goal(500, days_ago(5)), curve, TODAY)
    assert settled["missed_known"] == 95 and goals.status(settled) == goals.MISSED
    # known words reached after the goal's date don't count
    assert goals.settle(goal(99, days_ago(5)), curve, TODAY)["missed_known"] == 95


def test_settle_active():
    curve = {days_ago(n): 100 - n for n in range(20)}
    assert goals.status(goals.settle(goal(500, TODAY), curve, TODAY)) == goals.ACTIVE
    # known words before the goal was set don't reach it
    assert goals.status(goals.settle(goal(90, TODAY + timedelta(days=5), created=TODAY), {**curve, TODAY: 85}, TODAY)) == goals.ACTIVE


def test_current_goal():
    goals_ = [goal(500, TODAY + timedelta(days=90)), goal(300, TODAY + timedelta(days=30)),
              goal(200, days_ago(3), reached_on=days_ago(5).isoformat())]
    assert goals.current(goals_)["words"] == 300
    assert goals.current(goals_[2:]) is None
