from dataclasses import dataclass


@dataclass(frozen=True)
class StudyLanguage:
    """A language the user can study: dictionaries, saved words and cards belong to one."""

    key: str
    name: str
    native_name: str
    # Written without spaces between words: a lookup tries every substring from the cursor.
    without_spaces: bool = False
    chinese: bool = False


STUDY_LANGUAGES: tuple[StudyLanguage, ...] = (
    StudyLanguage("zh", "Mandarin", "中文", without_spaces=True, chinese=True),
    StudyLanguage("yue", "Cantonese", "粵語", without_spaces=True, chinese=True),
    StudyLanguage("ja", "Japanese", "日本語", without_spaces=True),
    StudyLanguage("ko", "Korean", "한국어"),
    StudyLanguage("en", "English", "English"),
    StudyLanguage("fr", "French", "Français"),
    StudyLanguage("de", "German", "Deutsch"),
    StudyLanguage("es", "Spanish", "Español"),
    StudyLanguage("it", "Italian", "Italiano"),
    StudyLanguage("pt", "Portuguese", "Português"),
    StudyLanguage("pl", "Polish", "Polski"),
    StudyLanguage("vi", "Vietnamese", "Tiếng Việt"),
    StudyLanguage("ru", "Russian", "Русский"),
    StudyLanguage("nan", "Taiwanese Hokkien (Taigi)", "台語", without_spaces=True, chinese=True),
)

# English name of each study language, by key.
LANGUAGES: dict[str, str] = {language.key: language.name for language in STUDY_LANGUAGES}
NATIVE_NAMES: dict[str, str] = {language.key: language.native_name for language in STUDY_LANGUAGES}
NO_SPACE_LANGUAGES: frozenset[str] = frozenset(language.key for language in STUDY_LANGUAGES if language.without_spaces)
CHINESE_LANGUAGES: frozenset[str] = frozenset(language.key for language in STUDY_LANGUAGES if language.chinese)
