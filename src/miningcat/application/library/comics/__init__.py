"""The comics and manga of the reader's library."""
from miningcat.application.library.comics.comic_settings import DEFAULT_SETTINGS, get_settings, save_settings
from miningcat.application.library.comics.library import (
    ARCHIVE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    IMPORT_EXTENSIONS,
    append_image,
    comic_folder,
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
from miningcat.application.library.comics.ocr import (
    ocr_language,
    ocr_unavailable,
    page_text,
    page_texts,
    read_all_pages,
    text_state,
)
from miningcat.application.library.comics.progress import (
    get_prefs,
    get_progress,
    right_to_left,
    save_prefs,
    save_progress,
)
from miningcat.domain.library.errors import ComicError

__all__ = [
    "ARCHIVE_EXTENSIONS", "ComicError", "IMAGE_EXTENSIONS", "IMPORT_EXTENSIONS", "append_image", "DEFAULT_SETTINGS", "comic_folder", "comics_dir", "delete_comic", "get_meta", "get_prefs",
    "get_progress", "get_settings", "import_file", "import_stream", "is_archive", "list_comics", "ocr_language", "ocr_unavailable",
    "page_path", "page_text", "page_texts", "read_all_pages", "right_to_left", "save_prefs", "save_progress", "save_settings",
    "text_state", "thumb_path",
]
