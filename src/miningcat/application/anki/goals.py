"""The vocabulary goals of a language (Settings › User preferences: "I want to know N words by a date") and where the
user stands, for the home page: the history of their known words and of their goals, reached or missed, their pace,
and what it takes to reach the nearest goal.

The history comes from two places: the days recorded in the database (known_history, exact), and before them the day
each known word became known, read from the Anki review log (the day one of its cards reached the known interval) or,
for the words marked known by hand, from the database."""
from datetime import date, datetime, timedelta

from miningcat.application.anki.config import anki, get_config
from miningcat.application.anki.reviews import card_notes, existing_decks, language_decks, review_days
from miningcat.application.mining import words
from miningcat.domain.cards import reviews
from miningcat.domain.cards.errors import AnkiError
from miningcat.domain.languages import LANGUAGES
from miningcat.domain.words import goals
from miningcat.domain.words.status import WordError
from miningcat.infrastructure.anki.ankiconnect import AnkiConnect
from miningcat.infrastructure.persistence.card_repository import CardRepository
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.persistence.word_repository import WordRepository

# {language: [{id, words, by (ISO date), created (ISO date), reached_on (ISO date) or missed_known (words known on
# its date) once settled}]}
_SETTING = "vocabulary_goals"
MAX_WORDS = 1_000_000
# The last plan made for each language ({language: summary()}): the home page shows it at once, then the new one.
_PLANS = "goal_plans"
# The shape of a summary: a cached one of another version is made again (the home page reads this one).
SUMMARY_VERSION = 6


def _all_goals() -> dict[str, list[dict]]:
    saved = settings.get(_SETTING, {}) or {}
    return {language: goals_ for language, goals_ in saved.items() if isinstance(goals_, list)}


def get_goals(language: str) -> list[dict]:
    """The goals of a language, by date, each with its status (active, reached, missed)."""
    return sorted(({**goal, "status": goals.status(goal)} for goal in _all_goals().get(language, [])),
                  key=lambda goal: (goal["by"], goal["words"]))


def _save_goals(language: str, language_goals: list[dict]) -> None:
    all_goals = _all_goals()
    all_goals[language] = [{key: value for key, value in goal.items() if key != "status"} for goal in language_goals]
    settings.set(_SETTING, all_goals)


def add_goal(language: str, words_goal, by, today: date | None = None) -> dict:
    """A new goal: more words than known now, by a day after today."""
    if language not in LANGUAGES:
        raise WordError(f"Unknown language: {language}")
    try:
        count, day = int(words_goal), date.fromisoformat(str(by))
    except (TypeError, ValueError):
        raise WordError("A goal is a number of words and a date.")
    if not 0 < count <= MAX_WORDS:
        raise WordError(f"A goal is between 1 and {MAX_WORDS:,} words.")
    today = today or reviews.anki_day(datetime.now())
    if day <= today:
        raise WordError("The goal's date has to be after today.")
    known = words.counts().get(language, {}).get("known", 0)
    if count <= known:
        raise WordError(f"You already know {known:,} words: aim for more.")
    language_goals = _all_goals().get(language, [])
    goal = {"id": max((g["id"] for g in language_goals), default=0) + 1, "words": count, "by": day.isoformat(),
            "created": today.isoformat()}
    _save_goals(language, [*language_goals, goal])
    return {**goal, "status": goals.ACTIVE}


def delete_goal(language: str, goal_id: int) -> None:
    _save_goals(language, [goal for goal in _all_goals().get(language, []) if goal["id"] != goal_id])




def _day(review_id: int) -> date:
    return reviews.anki_day(datetime.fromtimestamp(review_id / 1000))


def _anki_state(client: AnkiConnect, language: str, known_interval: int, today: date) -> dict:
    """What Anki tells of the language's decks: when each card was first seen and became known, the day each note was
    first seen and became known, the new cards waiting, the decks' limit of new cards a day and the new cards seen a
    day of late."""
    decks, top = existing_decks(client, language_decks(language))
    history = review_days.cards(client, decks)
    first_seen = {card: _day(h.first) for card, h in history.items()}
    matured = {card: _day(reached) for card, h in history.items() if (reached := h.reached(known_interval)) is not None}
    notes = card_notes.of(client, list(first_seen))

    def by_note(days: dict[int, date]) -> dict[int, date]:
        earliest: dict[int, date] = {}
        for card, day in days.items():
            note = notes.get(card)
            if note is not None:
                earliest[note] = min(day, earliest.get(note, day))
        return earliest

    since = today - timedelta(days=goals.PACE_DAYS)
    backlog = new_per_day = 0
    for deck in top:
        waiting, limit = _new_cards(client, deck, [d for d in decks if reviews.in_deck(d, deck)])
        backlog += waiting
        new_per_day += limit
    return {"decks": top, "first_seen": first_seen, "matured": matured, "note_known": by_note(matured),
            "note_first": by_note(first_seen), "backlog": backlog, "new_per_day": new_per_day,
            "seen_per_day": sum(day > since for day in first_seen.values()) / goals.PACE_DAYS}


def _new_cards(client: AnkiConnect, top: str, decks: list[str]) -> tuple[int, int]:
    """(new cards waiting, new cards a day) of a deck and its subdecks (`decks`, itself included), studied from it:
    its own limit caps them all, and only the decks holding new cards count, each up to its own limit."""
    limits: dict[str, int] = {}
    waiting = top_limit = 0
    for deck in decks:
        own = len(client.invoke("findCards", query=f'"deck:{deck}" -"deck:{deck}::*" is:new -is:suspended'))
        limit = int((client.invoke("getDeckConfig", deck=deck) or {}).get("new", {}).get("perDay") or 0)
        waiting += own
        if deck == top or own:
            limits[deck] = limit if own else 0
        if deck == top:
            top_limit = limit
    holding = sum(limits.values())
    return waiting, min(top_limit, holding) if holding else top_limit


def _known_day(word: dict, note_known: dict[int, date], lag: int) -> date:
    """The day a known word became known: from its Anki cards, else the day it was marked known (by hand), else for a
    word synced from Anki whose reviews aren't in the decks read, `lag` days after its note was made."""
    if word["anki_note_id"] in note_known:
        return note_known[word["anki_note_id"]]
    updated = reviews.anki_day(datetime.fromtimestamp(word["updated"]))
    if word["source"] == "manual":
        return updated
    return min(updated, reviews.anki_day(datetime.fromtimestamp(word["added"])) + timedelta(days=lag))


def cached_summary(language: str) -> dict:
    """The last summary made for the language, while its goals haven't changed since; else a new one."""
    last = (settings.get(_PLANS, {}) or {}).get(language)
    if last and last.get("version") == SUMMARY_VERSION and last.get("goals") == get_goals(language):
        return last
    return summary(language)


def _plan_json(goal: dict, plan: dict, measured: bool) -> dict:
    """A goal's plan for the home page: with the goal, dates as ISO, and whether lag and success were measured on the
    user's cards (else the usual values)."""
    return {"goal": goal, **{key: value.isoformat() if isinstance(value, date) else value for key, value in plan.items()},
            "measured": measured}


def summary(language: str, now: datetime | None = None) -> dict:
    """{goals: []} without any goal. Else {goals (each with its status, settled from the history: reached or missed),
    version (SUMMARY_VERSION), today, anki: {linked, connected, error?, decks?}, pace (known words a day), plans: one
    per active goal, the nearest first ({goal, ...plan}, see domain/words/goals.py, dates as ISO; the first is the
    current goal's),
    needs: what it takes to reach them all (goals.combine(), None without an active goal), steps: the pace it takes to
    reach them all ([[ISO date, words, goal id or None for today]], goals.needed_steps()), history: [[ISO date, known
    words]] of every day, forecast: [[ISO date, known words]] of every day from today to the last goal's date (at least
    two weeks) with the words in learning and the decks' limit of new cards a day (goals.forecast(), None without
    Anki), maturity: the share of new cards known at once, within a week, a month, in the end (None when not measured
    on the user's cards)}."""
    language_goals = _all_goals().get(language, [])
    if not language_goals:
        return {"goals": []}
    today = reviews.anki_day(now or datetime.now())
    known = words.record_known(language, today)  # the curve's today too
    with database.session() as conn:
        repository = WordRepository(conn)
        known_words = repository.known_words(language)
        snapshots = {date.fromisoformat(day): n for day, n in repository.known_history(language).items()}
        counts = repository.counts().get(language, {})
        learning_notes = repository.learning_notes(language)
        pending = CardRepository(conn).count("pending", language)

    config = get_config()
    state, status = None, {"linked": bool(language_decks(language)), "connected": False}
    if status["linked"]:
        try:
            state = _anki_state(anki(), language, config["known_interval"], today)
            status.update(connected=True, decks=state["decks"])
        except AnkiError as exc:
            status["error"] = str(exc)
    lag, success, sample = goals.maturity(state["first_seen"], state["matured"], today) if state else (goals.DEFAULT_LAG, goals.DEFAULT_SUCCESS, 0)

    note_known = state["note_known"] if state else {}
    curve = goals.known_curve([_known_day(w, note_known, lag) for w in known_words], snapshots, today)
    # A goal is settled for good: not from guessed days, when Anki should tell them but doesn't answer.
    settled = language_goals
    if state is not None or not status["linked"]:
        settled = [goals.settle(goal, curve, today) for goal in language_goals]
        if settled != language_goals:
            _save_goals(language, settled)
    active = [{**g, "status": goals.ACTIVE} for g in goals.active(settled)]
    current_pace = goals.pace(curve, today)
    plans, needs, steps, forecast, maturity = [], None, [], None, None
    if active:
        # With Anki, the words in learning are the ones whose cards were seen: the others are new cards, in the
        # backlog.
        learning_ages, within = None, None
        if state:
            learning_ages = tuple((today - state["note_first"][note]).days
                                  for note in learning_notes if note in state["note_first"])
            within = goals.known_within(state["first_seen"], state["matured"], today)
            if within:
                share = lambda days: round(within[min(days, len(within) - 1)], 2)
                maturity = {"at_once": share(0), "week": share(7), "month": share(30), "final": share(len(within))}
        pipeline = goals.Pipeline(
            known=known, learning=counts.get("learning", 0),
            backlog=state["backlog"] + pending if state else None, new_per_day=state["new_per_day"] if state else None,
            learning_ages=learning_ages, known_within=within, seen_per_day=state["seen_per_day"] if state else None,
            lag=lag, success=success)
        targets = [goals.Goal(g["words"], date.fromisoformat(g["by"])) for g in active]
        plans = [goals.plan(target, pipeline, current_pace, today) for target in targets]
        needs = goals.combine(plans)
        steps = [[day.isoformat(), words, None if index is None else active[index]["id"]]
                 for day, words, index in goals.needed_steps(known, targets, today)]
        days = max(14, *((target.by - today).days for target in targets))
        points = goals.forecast(pipeline, today, days)
        forecast = None if points is None else [[day.isoformat(), round(words)] for day, words in points]
    measured = sample >= goals.MIN_SAMPLE
    result = {
        "version": SUMMARY_VERSION, "goals": get_goals(language), "today": today.isoformat(),
        "anki": status, "pace": round(current_pace, 2),
        "plans": [_plan_json(g, plan, measured) for g, plan in zip(active, plans)],
        "needs": needs, "steps": steps, "history": [[day.isoformat(), n] for day, n in curve.items()],
        "forecast": forecast, "maturity": maturity,
    }
    cache = settings.get(_PLANS, {}) or {}
    cache[language] = result
    settings.set(_PLANS, cache)
    return result
