"""Where the user stopped in each comic, and its preferences (language, reading direction)."""
import re
import time

from miningcat.application.library.comics.library import comic_folder, get_meta
from miningcat.domain.languages import language_key
from miningcat.domain.library.errors import ComicError
from miningcat.infrastructure.files.json_files import read_json, write_json

# Languages whose comics read right to left by default (manga, and their Chinese editions).
RIGHT_TO_LEFT_LANGUAGES = ("ja", "zh", "yue")


def get_progress(comic_id: str) -> dict:
    return read_json(comic_folder(comic_id) / "progress.json", {})


def save_progress(comic_id: str, page) -> dict:
    count = len(get_meta(comic_id)["pages"])
    try:
        page = max(1, min(count, int(page)))
    except (TypeError, ValueError):
        raise ComicError("Invalid page.")
    progress = {"page": page, "percent": round(page / count * 100, 2), "updated": time.time()}
    write_json(comic_folder(comic_id) / "progress.json", progress)
    return progress


def get_prefs(comic_id: str) -> dict:
    return read_json(comic_folder(comic_id) / "prefs.json", {})


def save_prefs(comic_id: str, values: dict) -> dict:
    get_meta(comic_id)
    prefs = get_prefs(comic_id)
    if "language" in values:
        language = str(values["language"] or "").strip()
        if language and not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*", language):
            raise ComicError("Invalid language tag.")
        prefs["language"] = language
    if "direction" in values:
        if values["direction"] not in ("", "rtl", "ltr"):
            raise ComicError("Invalid reading direction.")
        prefs["direction"] = values["direction"]
    write_json(comic_folder(comic_id) / "prefs.json", prefs)
    return prefs


def right_to_left(comic_id: str, language: str) -> bool:
    direction = get_prefs(comic_id).get("direction")
    if direction:
        return direction == "rtl"
    return language_key(language) in RIGHT_TO_LEFT_LANGUAGES
