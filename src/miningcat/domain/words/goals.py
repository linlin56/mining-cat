"""Vocabulary goals: "I want to know N words by a date". When it will happen at the current pace, how many new cards a
day it takes, and how many cards to mine a day to always have enough new cards waiting in Anki.

A card shown for the first time today only becomes known (mature) days or weeks later, and some never do. With Anki,
the plan counts with the user's own share of new cards known within each number of days (`known_within`, read from
their review log): some are known at once (a word already known, answered Easy), most after weeks. Without it, with a
usual delay (`lag`) and share of the cards that become known (`success`)."""
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

# Without enough of the user's own cards to measure them: a usual delay before a card is mature (21 days of
# interval after a few weeks of reviews), and a usual share of the cards that get there.
DEFAULT_LAG = 35
DEFAULT_SUCCESS = 0.85
# The fewest cards from which the user's own lag and success are used.
MIN_SAMPLE = 20
# The current pace: the words that became known in the last PACE_DAYS days.
PACE_DAYS = 30
# A card first seen less than that before today may still become known: not counted in the success rate.
SUCCESS_MARGIN = 30
# The success rate is measured on the cards first seen in the last year.
SUCCESS_WINDOW = 365


@dataclass(frozen=True)
class Goal:
    words: int
    by: date


@dataclass(frozen=True)
class Pipeline:
    """Where the user's words stand. `backlog`, `new_per_day`, `learning_ages` and `seen_per_day` are None when Anki
    doesn't tell them, `known_within` when there are too few cards to measure it."""
    known: int
    learning: int                    # words in learning, without Anki: when they'll be known isn't told, all count
    backlog: int | None = None       # new cards not seen yet (in Anki, and made in MiningCat but not sent yet)
    new_per_day: int | None = None   # the decks' limit of new cards a day
    # The days since each word in learning was first reviewed. Only the words whose cards were seen: a word whose
    # cards are all new is in the backlog, not in learning.
    learning_ages: tuple[int, ...] | None = None
    # [k]: the share of new cards known within k days of their first review (the last one for any later day)
    known_within: tuple[float, ...] | None = None
    seen_per_day: float | None = None  # the new cards first seen a day over the last PACE_DAYS days
    lag: int = DEFAULT_LAG
    success: float = DEFAULT_SUCCESS


def maturity(first_seen: dict[int, date], matured: dict[int, date], today: date) -> tuple[int, float, int]:
    """(lag, success, sample) from the cards' first review day and the day they became known (cards never known
    aren't in `matured`). The defaults when there are too few cards."""
    delays = [(matured[card] - first).days for card, first in first_seen.items() if card in matured]
    lag = round(median(delays)) if len(delays) >= MIN_SAMPLE else DEFAULT_LAG
    # The cards that had the time to become known: first seen in the last year, but at least lag + a margin ago.
    oldest, newest = today - timedelta(days=SUCCESS_WINDOW), today - timedelta(days=lag + SUCCESS_MARGIN)
    cohort = [card for card, first in first_seen.items() if oldest <= first <= newest]
    success = sum(card in matured for card in cohort) / len(cohort) if len(cohort) >= MIN_SAMPLE else DEFAULT_SUCCESS
    return max(1, lag), max(0.05, success), len(delays)


def known_within(first_seen: dict[int, date], matured: dict[int, date], today: date) -> tuple[float, ...] | None:
    """[k]: the share of the new cards known within k days of their first review, from the cards first seen in the
    last year (None with too few cards known). A card not known yet only tells that it takes it more than its age: the
    shares are made like a survival curve (Kaplan-Meier), so that the recent cards, many not known yet, don't make it
    look slower or faster than it is. It stops where too few cards are old enough to tell more."""
    oldest = today - timedelta(days=SUCCESS_WINDOW)
    known, leaving = Counter(), Counter()  # by days after the first review: cards known, cards leaving the count
    at_risk = 0
    for card, first in first_seen.items():
        if first < oldest:
            continue
        at_risk += 1
        days = (matured[card] - first).days if card in matured else (today - first).days
        leaving[days] += 1
        if card in matured:
            known[days] += 1
    if sum(known.values()) < MIN_SAMPLE:
        return None
    shares, unknown = [], 1.0
    for days in range(max(leaving) + 1):
        if at_risk < MIN_SAMPLE:
            break
        unknown *= 1 - known[days] / at_risk
        shares.append(1 - unknown)
        at_risk -= leaving[days]
    return tuple(shares)


def known_curve(dates: list[date], snapshots: dict[date, int], today: date) -> dict[date, int]:
    """The number of known words at the end of each day, from the day each known word became known (`dates`, one per
    word known today) and the counts recorded on some days (`snapshots`, exact). The dates miss the words known then
    and forgotten since: so that the curve doesn't jump at each record, it goes through the records, straight from
    one to the next, the dates giving its shape before the first record (scaled to reach it) and after the last one
    (from it on)."""
    first = min([*dates, *snapshots], default=today)
    per_day: dict[date, int] = {}
    for day in dates:
        per_day[day] = per_day.get(day, 0) + 1
    rebuilt, total, day = {}, 0, first
    while day <= today:
        total += per_day.get(day, 0)
        rebuilt[day] = total
        day += timedelta(days=1)
    records = sorted((day, known) for day, known in snapshots.items() if first <= day <= today)
    if not records:
        return rebuilt
    (first_record, first_known), (last_record, last_known) = records[0], records[-1]
    curve = {}
    for day, count in rebuilt.items():
        if day <= first_record:
            reference = rebuilt[first_record]
            curve[day] = round(count * first_known / reference) if reference else 0
        elif day >= last_record:
            curve[day] = max(0, last_known + count - rebuilt[last_record])
    for (start, start_known), (end, end_known) in zip(records, records[1:]):
        span = (end - start).days
        for offset in range(1, span):
            curve[start + timedelta(days=offset)] = round(start_known + (end_known - start_known) * offset / span)
    curve.update(records)
    return dict(sorted(curve.items()))


def pace(curve: dict[date, int], today: date, days: int = PACE_DAYS) -> float:
    """Words known per day over the last `days` days (or since the first day of the curve, when it's younger)."""
    if not curve:
        return 0.0
    start = max(min(curve), today - timedelta(days=days))
    span = (today - start).days
    if span <= 0:
        return 0.0
    return max(0.0, (curve.get(today, curve[max(curve)]) - curve[start]) / span)


def _after(today: date, days: float) -> date | None:
    return today + timedelta(days=math.ceil(days)) if days < 36_500 else None


def _known_within(pipeline: Pipeline, days: int) -> float:
    """The share of new cards known within `days` days of their first review."""
    p = pipeline
    if days < 0:
        return 0.0
    if p.known_within is None:
        return p.success if days >= p.lag else 0.0
    return p.known_within[min(days, len(p.known_within) - 1)]


def _learning_known(pipeline: Pipeline, days: int) -> float:
    """The words in learning that should be known in `days` days: each one, from how long ago it was first seen
    (one seen long ago and not known yet is a hard one: it has less of a chance). Without Anki, all of them."""
    p = pipeline
    if p.learning_ages is None:
        return p.success * p.learning
    total = 0.0
    for age, count in Counter(p.learning_ages).items():
        known_by_now = _known_within(p, age)
        if known_by_now < 1:
            total += count * (_known_within(p, age + days) - known_by_now) / (1 - known_by_now)
    return total


def _new_known(pipeline: Pipeline, days: int) -> float:
    """The words known in `days` days for each new card a day seen from tomorrow on."""
    return sum(_known_within(pipeline, k) for k in range(days))


def forecast(pipeline: Pipeline, today: date, days: int) -> list[tuple[date, float]] | None:
    """The words that should be known each day of the next `days`, with the words in learning and the decks' limit
    of new cards a day (None without Anki)."""
    p = pipeline
    if p.learning_ages is None or p.new_per_day is None:
        return None
    points, new = [], 0.0
    for day in range(days + 1):
        points.append((today + timedelta(days=day), p.known + _learning_known(p, day) + p.new_per_day * new))
        new += _known_within(p, day)  # one more day of new cards, seen from tomorrow on
    return points


def _deck_eta(remaining: int, pipeline: Pipeline, today: date) -> date | None:
    """The day `remaining` more words are known with the words in learning and the decks' limit of new cards a day."""
    p = pipeline
    new = 0.0
    for day in range(36_500):
        if _learning_known(p, day) + p.new_per_day * new >= remaining - 1e-9:  # not missed by a rounding
            return today + timedelta(days=day)
        new += _known_within(p, day)
    return None


def plan(goal: Goal, pipeline: Pipeline, current_pace: float, today: date) -> dict:
    """What it takes to know `goal.words` words by `goal.by`. Counts are rounded up: a card can't be split."""
    p = pipeline
    remaining = max(0, goal.words - p.known)
    days_left = (goal.by - today).days
    # the words in learning that should be known by the goal's date, and the ones later
    learning = _learning_known(p, days_left)
    eventually = _learning_known(p, 36_500)
    result = {
        "remaining": remaining, "days_left": days_left, "reached": remaining == 0,
        "pace": round(current_pace, 2),
        "needed_pace": round(remaining / days_left, 2) if days_left > 0 else None,
        "eta": None,
        "lag": p.lag, "success": round(p.success, 2),
        "learning": round(learning), "learning_later": round(eventually - learning),
        "cards_needed": None, "new_per_day": None, "mine_per_day": None, "too_late": False,
        "backlog": p.backlog, "deck_new_per_day": p.new_per_day, "backlog_days": None, "deck_eta": None,
        "seen_per_day": None if p.seen_per_day is None else round(p.seen_per_day, 1),
        "raise_limit": False,
    }
    if remaining == 0:
        return result
    if current_pace > 0:
        result["eta"] = _after(today, remaining / current_pace)
    if p.new_per_day:
        result["deck_eta"] = _deck_eta(remaining, p, today)
        if p.backlog is not None:
            result["backlog_days"] = math.floor(p.backlog / p.new_per_day)
    # The learning words that should become known in time, then the new cards that make up for the rest: each new
    # card a day from tomorrow on gives that many words by the goal's date.
    missing = remaining - learning
    if missing <= 0:
        # the learning words are enough: no new card to see or mine
        result.update(cards_needed=0, new_per_day=0, mine_per_day=0 if p.backlog is not None else None)
        return result
    per_card = _new_known(p, days_left)
    if per_card <= 0:
        # a new card seen from tomorrow on can't be known by then
        result["too_late"] = True
        return result
    # the days whose new cards can be known by the goal's date, and the cards to see over them
    useful = sum(_known_within(p, k) > 0 for k in range(days_left))
    cards = math.ceil(missing * useful / per_card - 1e-9)
    new_per_day = math.ceil(cards / useful)
    result.update(cards_needed=cards, new_per_day=new_per_day)
    if p.backlog is not None:
        result["mine_per_day"] = math.ceil(max(0, cards - p.backlog) / useful)
    result["raise_limit"] = bool(p.new_per_day is not None and new_per_day > p.new_per_day)
    return result


def combine(plans: list[dict]) -> dict:
    """What it takes to reach all the active goals (`plans`, one per goal, by date): each count a day is the highest
    of the goals' (a count kept every day from today that reaches one goal reaches those that need less a day), with
    the goal it's for (its index in `plans`). Each count is None when no goal tells it: reached, too late, or without
    Anki. The goals
    too late for new cards to be known by their date (`too_late`, indexes) aren't in the counts of cards, but are in
    the pace of known words: words marked known by hand can still get there."""
    def highest(key: str, cards: bool) -> tuple[float | None, int | None]:
        known = [(plan[key], index) for index, plan in enumerate(plans)
                 if plan[key] is not None and not (cards and plan["too_late"])]
        return max(known) if known else (None, None)  # the farthest goal on a tie: the one that takes it longest

    new_per_day, new_for = highest("new_per_day", cards=True)
    mine_per_day, mine_for = highest("mine_per_day", cards=True)
    needed_pace, pace_for = highest("needed_pace", cards=False)
    deck = plans[0]["deck_new_per_day"] if plans else None  # the same for every goal
    return {"new_per_day": new_per_day, "new_for": new_for, "mine_per_day": mine_per_day, "mine_for": mine_for,
            "needed_pace": needed_pace, "pace_for": pace_for,
            "too_late": [index for index, plan in enumerate(plans) if plan["too_late"]],
            "raise_limit": bool(deck is not None and new_per_day is not None and new_per_day > deck)}


def needed_steps(known: int, goals: list[Goal], today: date) -> list[tuple[date, int, int | None]]:
    """The pace it takes to reach all the goals (by date), as points (day, words, index of the goal in `goals`) from
    today's known words: the steepest goal from today, then the steepest one from there, and so on. The goals under it
    are reached on the way. Its first slope is the highest needed pace of the goals (combine())."""
    steps: list[tuple[date, int, int | None]] = [(today, known, None)]
    rest = [(goal.by, goal.words, index) for index, goal in enumerate(goals) if goal.by > today and goal.words > known]
    while rest:
        day, words = steps[-1][:2]
        slope = lambda step: (step[1] - words) / (step[0] - day).days
        step = max(rest, key=lambda step: (slope(step), step[0]))  # the farthest goal on a tie
        if slope(step) <= 0:
            break
        steps.append(step)
        rest = [later for later in rest if later[0] > step[0]]
    return steps


# The statuses of a goal. Once reached or missed, a goal stays so: it's kept as the history of the user's goals.
ACTIVE, REACHED, MISSED = "active", "reached", "missed"


def status(goal: dict) -> str:
    if goal.get("reached_on"):
        return REACHED
    return MISSED if goal.get("missed_known") is not None else ACTIVE


def settle(goal: dict, curve: dict[date, int], today: date) -> dict:
    """The goal, reached on the first day from its creation to its date with enough known words, or missed once its
    date has passed (with the words known that day). Unchanged when it was already settled or is still going."""
    if status(goal) != ACTIVE:
        return goal
    created, by = date.fromisoformat(goal["created"]), date.fromisoformat(goal["by"])
    days = sorted(curve)
    reached = next((day for day in days if created <= day <= by and curve[day] >= goal["words"]), None)
    if reached is not None:
        return {**goal, "reached_on": reached.isoformat()}
    if by < today:
        before = [curve[day] for day in days if day <= by]
        return {**goal, "missed_known": before[-1] if before else 0}
    return goal


def active(goals: list[dict]) -> list[dict]:
    """The goals still to come, the nearest first."""
    return sorted((goal for goal in goals if status(goal) == ACTIVE), key=lambda goal: (goal["by"], goal["words"]))

