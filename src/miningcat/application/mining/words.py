import time

from miningcat.application.mining import preferences
from miningcat.domain.languages import CHINESE_LANGUAGES, LANGUAGES
from miningcat.domain.text.chinese_script import chinese_counterpart
from miningcat.domain.text.readings import normalize_reading
from miningcat.domain.words import forms
from miningcat.domain.words.status import DEFAULT_KNOWN_INTERVAL, STATUSES, WordError, status_from_interval
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.word_repository import WordRepository


def preferred_form(language: str, expression: str, preference: str | None = None) -> str:
    """The form under which a word is saved, given the script the user learns (`preference`, read from the
    settings when not given: pass it for many words)."""
    if language not in CHINESE_LANGUAGES:
        return expression
    return forms.preferred_form(language, expression, preference or preferences.chinese_script_preference(language))


def display_reading(language: str, reading: str) -> str:
    """The reading as the user wants to see it: zhuyin or pinyin, as chosen."""
    return forms.display_reading(language, reading, preferences.reading_system(language))


def status_of(language: str, expression: str, reading: str = "") -> dict:
    """Status of a word, and for Chinese the status of the same word in the other script."""
    with database.session() as conn:
        repository = WordRepository(conn)
        word = repository.find(language, expression, reading)
        result = {"status": word["status"] if word else "new", "source": word["source"] if word else None}
        if language in CHINESE_LANGUAGES:
            other = chinese_counterpart(expression, language)
            if other is not None:
                script, other_expression = other
                linked = repository.find(language, other_expression, reading)
                if linked and linked["status"] in ("learning", "known"):
                    result["linked"] = {"script": script, "expression": other_expression, "status": linked["status"]}
    return result


def set_status(language: str, expression: str, reading: str, status: str | None,
               source: str = "manual", anki_note_id: int | None = None, anki_interval: int | None = None) -> dict:
    """Sets (or with status=None, clears) the status of a word. Returns the new status."""
    if language not in LANGUAGES:
        raise WordError(f"Unknown language: {language}")
    if status is not None and status not in STATUSES:
        raise WordError(f"Unknown status: {status}")
    expression = (expression or "").strip()
    if not expression:
        raise WordError("Missing word.")
    reading = normalize_reading(reading, language)
    now = time.time()
    with database.session() as conn:
        repository = WordRepository(conn)
        word = repository.find(language, expression, reading)
        if status is None:
            if word:
                repository.delete(word["id"])
            return {"status": "new"}
        if word:
            repository.update(word["id"], status, source, reading, anki_note_id, anki_interval, now)
        else:
            repository.insert(language, expression, reading, status, source, anki_note_id, anki_interval, now)
    return {"status": status}


def list_words(language: str | None = None, status: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    with database.session() as conn:
        return WordRepository(conn).search(language, status, limit, offset)


def counts() -> dict:
    with database.session() as conn:
        return WordRepository(conn).counts()


def statuses_for(language: str, expressions: list[str]) -> dict[str, str]:
    """Status of many expressions at once (any reading), e.g. to colour a text."""
    with database.session() as conn:
        return WordRepository(conn).statuses_for(language, expressions)


def apply_anki_state(language: str, expression: str, reading: str, note_id: int | None,
                     interval: int, known_interval: int = DEFAULT_KNOWN_INTERVAL) -> str:
    """Updates a word from its Anki cards. A word the user marked known or ignored stays as it is."""
    status = status_from_interval(interval, known_interval)
    with database.session() as conn:
        word = WordRepository(conn).find(language, expression, reading)
    if word and word["source"] == "manual" and word["status"] in ("known", "ignored"):
        return word["status"]
    set_status(language, expression, reading, status, source="anki", anki_note_id=note_id, anki_interval=interval)
    return status
