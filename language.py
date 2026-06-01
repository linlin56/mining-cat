# language.py -- Supported languages and their associated constants.

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class LangConfig:
    label: str
    whisper_code: str
    iso639_2: str  # ISO 639-2 code used for MP4 subtitle track metadata
    closing_punct: frozenset
    # Regex pattern for in-text vocabulary annotations to strip before alignment.
    vocab_annotation_pattern: str


class Language(Enum):
    MANDARIN_TW = LangConfig(
        label='Mandarin — Taiwan (Traditionnal)',
        whisper_code='zh',
        iso639_2='zho',
        closing_punct=frozenset('。？！」'),
        vocab_annotation_pattern=r'\[\d+\]',
    )
    MANDARIN_CN = LangConfig(
        label='Mandarin — China (Simplified)',
        whisper_code='zh',
        iso639_2='zho',
        closing_punct=frozenset('。？！」”'),
        vocab_annotation_pattern=r'\[\d+\]',
    )
    JAPANESE = LangConfig(
        label='Japanese',
        whisper_code='ja',
        iso639_2='jpn',
        closing_punct=frozenset('。？！」』）'),
        vocab_annotation_pattern=r'\[\d+\]',
    )
    # TODO : Add more! Priorities are languages that me (the owner) can understand enough to test
    JAPANESE = LangConfig(
        label="Japanese",
        whisper_code="ja",
        closing_punct=frozenset('。？！』」'),
        vocab_annotation_pattern=r'［＃.+?］', # Pattern for Aozora Bunko style notes
    )
    # TODO : Add more!

    @classmethod
    def from_id(cls, lang_id: str) -> 'Language':
        for lang in cls:
            if lang.name.lower() == lang_id.lower():
                return lang
        raise ValueError(f'Unknown language id: {lang_id!r}')

    @classmethod
    def from_label(cls, label: str) -> 'Language':
        for lang in cls:
            if lang.value.label == label:
                return lang
        raise ValueError(f'Unknown language label: {label!r}')

    @classmethod
    def all_labels(cls) -> list[str]:
        return [lang.value.label for lang in cls]

    @classmethod
    def ids(cls) -> list[str]:
        return [lang.name.lower() for lang in cls]
