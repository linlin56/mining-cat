"""The comics and manga of the reader's library."""
from miningcat.application.library.comics.comic_settings import DEFAULT_SETTINGS, get_settings, save_settings
from miningcat.application.library.comics.library import (
    ARCHIVE_EXTENSIONS,
    comics_dir,
    delete_comic,
    get_meta,
    import_file,
    import_stream,
    is_archive,
    list_comics,
    page_path,
    thumb_path,
)
from miningcat.application.library.comics.ocr import ocr_language, page_text
from miningcat.application.library.comics.progress import (
    get_prefs,
    get_progress,
    right_to_left,
    save_prefs,
    save_progress,
)
from miningcat.domain.library.errors import ComicError

__all__ = [
    "ARCHIVE_EXTENSIONS", "ComicError", "DEFAULT_SETTINGS", "comics_dir", "delete_comic", "get_meta", "get_prefs",
    "get_progress", "get_settings", "import_file", "import_stream", "is_archive", "list_comics", "ocr_language",
    "page_path", "page_text", "right_to_left", "save_prefs", "save_progress", "save_settings", "thumb_path",
]
