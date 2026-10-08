import shutil
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.dictionary.errors import DictionaryError
from miningcat.domain.languages import LANGUAGES
from miningcat.infrastructure.persistence.database import database
from miningcat.infrastructure.persistence.dictionary_repository import DictionaryRepository


def list_dictionaries() -> list[dict]:
    with database.session() as conn:
        return DictionaryRepository(conn).all()


def get_dictionary(dict_id: int) -> dict:
    with database.session() as conn:
        dictionary = DictionaryRepository(conn).get(dict_id)
    if dictionary is None:
        raise DictionaryError("Unknown dictionary.")
    return dictionary


def update_dictionary(dict_id: int, enabled: bool | None = None, language: str | None = None) -> dict:
    get_dictionary(dict_id)
    with database.session() as conn:
        repository = DictionaryRepository(conn)
        if enabled is not None:
            repository.set_enabled(dict_id, enabled)
        if language is not None:
            if language not in LANGUAGES:
                raise DictionaryError(f"Unsupported language: {language}")
            repository.set_language(dict_id, language)
    return get_dictionary(dict_id)


def reorder(dict_ids: list[int]) -> None:
    """Sets the lookup order of the dictionaries: the first one comes first in the results."""
    with database.session() as conn:
        repository = DictionaryRepository(conn)
        for position, dict_id in enumerate(dict_ids):
            repository.set_priority(int(dict_id), position)


def delete_dictionary(dict_id: int) -> None:
    with database.session() as conn:
        DictionaryRepository(conn).delete(dict_id)
    shutil.rmtree(paths.dictionary_media(dict_id), ignore_errors=True)


def media_path(dict_id: int, ref: str) -> Path:
    """An image of a dictionary's glossaries."""
    base = paths.dictionary_media(dict_id).resolve()
    path = (base / ref).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise DictionaryError("No such image.")
    return path
