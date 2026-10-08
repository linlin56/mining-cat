"""Languages: the study languages (dictionaries, words, cards) and the converter's language variants."""
from miningcat.domain.languages.language import Language
from miningcat.domain.languages.profile import LanguageProfile, Voice, WordSegmentation
from miningcat.domain.languages.study_language import (
    CHINESE_LANGUAGES, LANGUAGES, NATIVE_NAMES, NO_SPACE_LANGUAGES, STUDY_LANGUAGES, StudyLanguage,
)
from miningcat.domain.languages.tags import is_no_space, language_key, same_family

__all__ = [
    "Language", "LanguageProfile", "Voice", "WordSegmentation", "StudyLanguage", "STUDY_LANGUAGES",
    "LANGUAGES", "NATIVE_NAMES", "NO_SPACE_LANGUAGES", "CHINESE_LANGUAGES", "language_key", "is_no_space",
    "same_family",
]
