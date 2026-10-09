STATUSES = ("learning", "known", "ignored")
# Interval (days) from which a card counts as known: Anki's definition of a mature card.
DEFAULT_KNOWN_INTERVAL = 21


class WordError(ValueError):
    pass


def status_from_interval(interval: int, known_interval: int = DEFAULT_KNOWN_INTERVAL) -> str:
    """The status of a word from the interval of its Anki cards."""
    return "known" if interval >= known_interval else "learning"
