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


def test_plan_with_enough_learning_words_close_to_the_date():
    pipeline = Pipeline(known=900, learning=200, backlog=0, lag=35, success=1.0)
    plan = goals.plan(Goal(1000, TODAY + timedelta(days=20)), pipeline, 5.0, TODAY)
    # too close for new cards, but none is needed: not "too late", nor "nothing to tell"
    assert not plan["reached"] and not plan["too_late"] and plan["new_per_day"] == 0 and plan["mine_per_day"] == 0


def test_plan_reached():
    plan = goals.plan(Goal(500, TODAY + timedelta(days=20)), Pipeline(known=600, learning=0), 5.0, TODAY)
    assert plan["reached"] is True and plan["remaining"] == 0 and plan["cards_needed"] is None


def test_combine_takes_the_most_demanding_goal():
    pipeline = Pipeline(known=100, learning=500, backlog=50, new_per_day=20, lag=30, success=1.0)
    near = goals.plan(Goal(400, TODAY + timedelta(days=40)), pipeline, 5.0, TODAY)
    far = goals.plan(Goal(3100, TODAY + timedelta(days=130)), pipeline, 5.0, TODAY)
    # the learning words are enough for the nearest goal, not for the farthest one
    assert near["new_per_day"] == 0 and near["mine_per_day"] == 0
    needs = goals.combine([near, far])
    assert needs["new_per_day"] == far["new_per_day"] == 25 and needs["new_for"] == 1
    assert needs["mine_per_day"] == far["mine_per_day"] == 25 and needs["mine_for"] == 1
    assert needs["needed_pace"] == far["needed_pace"] and needs["pace_for"] == 1 and needs["raise_limit"] is True


def test_combine_without_counts():
    pipeline = Pipeline(known=100, learning=0, lag=30)
    needs = goals.combine([goals.plan(Goal(500, TODAY + timedelta(days=20)), pipeline, 5.0, TODAY)])  # too late
    assert needs["new_per_day"] is None and needs["new_for"] is None and needs["mine_per_day"] is None
    assert needs["too_late"] == [0] and needs["needed_pace"] == 20  # 400 words in 20 days


def test_combine_leaves_out_the_goals_too_late():
    pipeline = Pipeline(known=100, learning=0, backlog=1000, new_per_day=20, lag=30, success=1.0)
    near = goals.plan(Goal(150, TODAY + timedelta(days=10)), pipeline, 5.0, TODAY)
    far = goals.plan(Goal(500, TODAY + timedelta(days=100)), pipeline, 5.0, TODAY)
    needs = goals.combine([near, far])
    # enough cards waiting for the far goal, but none can be known in time for the near one: not "enough for all"
    assert needs["mine_per_day"] == 0 and needs["mine_for"] == 1 and needs["too_late"] == [0]
    # known words can still get there (marked known by hand): the near goal's pace, higher, counts
    assert needs["needed_pace"] == near["needed_pace"] == 5 and needs["pace_for"] == 0


def test_needed_steps():
    in_days = lambda days: TODAY + timedelta(days=days)
    # the near goal is under the line to the far one: reached on the way
    targets = [Goal(400, in_days(40)), Goal(3100, in_days(130))]
    steps = goals.needed_steps(100, targets, TODAY)
    assert steps == [(TODAY, 100, None), (in_days(130), 3100, 1)]
    # its first slope is the pace combine() tells
    plans = [goals.plan(target, Pipeline(known=100, learning=0), 5.0, TODAY) for target in targets]
    assert goals.combine(plans)["needed_pace"] == round(3000 / 130, 2)
    # a steep near goal: to it, then on to the far one; a goal already known isn't on it
    steps = goals.needed_steps(100, [Goal(90, in_days(10)), Goal(1000, in_days(20)), Goal(1500, in_days(130))], TODAY)
    assert [index for _, _, index in steps] == [None, 1, 2]


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


def test_active_goals():
    goals_ = [goal(500, TODAY + timedelta(days=90)), goal(300, TODAY + timedelta(days=30)),
              goal(200, days_ago(3), reached_on=days_ago(5).isoformat())]
    assert goals.active(goals_[2:]) == []
    assert [g["words"] for g in goals.active(goals_)] == [300, 500]
