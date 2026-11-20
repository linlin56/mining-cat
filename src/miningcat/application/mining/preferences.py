from miningcat.domain.languages import CHINESE_LANGUAGES
from miningcat.domain.words.forms import READING_SYSTEMS, SCRIPTS
from miningcat.domain.words.status import WordError
from miningcat.infrastructure.persistence.settings_store import settings

_SCRIPTS_SETTING = "chinese_scripts"            # {language: traditional, simplified or both}
_READING_SYSTEMS_SETTING = "reading_systems"    # {"zh": pinyin or zhuyin, "nan": tailo or poj}
_TAIWAN_READINGS_SETTING = "taiwan_readings"    # True: MiningCat's Taiwan readings win over the dictionaries'


def taiwan_readings() -> bool:
    """Whether the Mandarin readings are forced to the Taiwan ones of MiningCat's list."""
    return bool(settings.get(_TAIWAN_READINGS_SETTING, False))


def set_taiwan_readings(enabled: bool) -> None:
    settings.set(_TAIWAN_READINGS_SETTING, bool(enabled))


def taiwan_readings_apply(language: str) -> bool:
    return language == "zh" and taiwan_readings()


def chinese_script_preference(language: str) -> str:
    """The Chinese script the user learns: words are saved in it."""
    return (settings.get(_SCRIPTS_SETTING, {}) or {}).get(language, "both")


def set_chinese_script_preference(language: str, script: str) -> None:
    if language not in CHINESE_LANGUAGES or script not in SCRIPTS:
        raise WordError("Invalid script setting.")
    prefs = settings.get(_SCRIPTS_SETTING, {}) or {}
    prefs[language] = script
    settings.set(_SCRIPTS_SETTING, prefs)


def reading_system(language: str) -> str:
    """How Mandarin and Taigi readings are shown ("" for other languages)."""
    if language not in READING_SYSTEMS:
        return ""
    return (settings.get(_READING_SYSTEMS_SETTING, {}) or {}).get(language, READING_SYSTEMS[language][0])


def set_reading_system(language: str, system: str) -> None:
    if system not in READING_SYSTEMS.get(language, ()):
        raise WordError("Invalid reading setting.")
    prefs = settings.get(_READING_SYSTEMS_SETTING, {}) or {}
    prefs[language] = system
    settings.set(_READING_SYSTEMS_SETTING, prefs)
