class AnkiError(Exception):
    """Anki refused something, or the Anki setup is incomplete: shown to the user as is."""


class AnkiUnavailable(AnkiError):
    """Anki isn't running, or AnkiConnect isn't installed."""


class MediaUnavailable(AnkiError):
    """A media link of a card couldn't be downloaded (offline, the site refusing for now): it's tried again later."""
