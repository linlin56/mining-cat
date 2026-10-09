"""The reader's library of books."""
from miningcat.application.library.books.importers import split_text_chapters
from miningcat.application.library.books.library import (
    BOOK_EXTENSIONS,
    book_folder,
    books_dir,
    chapter_html,
    chapter_text,
    delete_book,
    get_meta,
    get_prefs,
    get_progress,
    import_book,
    list_books,
    resource_path,
    save_prefs,
    save_progress,
)
from miningcat.application.library.books.reader_settings import DEFAULT_SETTINGS, get_settings, save_settings
from miningcat.domain.library.errors import BookError
from miningcat.domain.text.decoding import decode_text
from miningcat.domain.text.language_detection import detect_language

__all__ = [
    "BOOK_EXTENSIONS", "BookError", "DEFAULT_SETTINGS", "book_folder", "books_dir", "chapter_html", "chapter_text",
    "decode_text", "delete_book", "detect_language", "get_meta", "get_prefs", "get_progress", "get_settings",
    "import_book", "list_books", "resource_path", "save_prefs", "save_progress", "save_settings",
    "split_text_chapters",
]
