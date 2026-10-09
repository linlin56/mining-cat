class LibraryError(ValueError):
    """Something of a library that can't be done: shown to the user as is."""


class BookError(LibraryError):
    pass


class ComicError(LibraryError):
    pass


class VideoError(LibraryError):
    pass


class AudioError(LibraryError):
    """The audio of a converted book."""
