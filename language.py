# language.py — Supported languages and their associated constants.

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class LangConfig:
    label: str
    whisper_code: str
    closing_punct: frozenset
    # Regex pattern for in-text vocabulary annotations to strip before alignment.
    vocab_annotation_pattern: str


class Language(Enum):
    MANDARIN_TW = LangConfig(
        label="Mandarin — Taiwan (Traditionnal)",
        whisper_code="zh",
        closing_punct=frozenset('。？！」'),
        vocab_annotation_pattern=r'\[\d+\]',
    )
    MANDARIN_CN = LangConfig(
        label="Mandarin — Chine (Simplified)",
        whisper_code="zh",
        closing_punct=frozenset('。？！」”'),
        vocab_annotation_pattern=r'\[\d+\]',
    )
    # TODO : Add more! Priorities are languages that me (the owner) can understand enough to test

    @classmethod
    def from_id(cls, lang_id: str) -> "Language":
        for lang in cls:
            if lang.name.lower() == lang_id.lower():
                return lang
        raise ValueError(f"Unknown language id: {lang_id!r}")

    @classmethod
    def from_label(cls, label: str) -> "Language":
        for lang in cls:
            if lang.value.label == label:
                return lang
        raise ValueError(f"Unknown language label: {label!r}")

    @classmethod
    def all_labels(cls) -> list[str]:
        return [lang.value.label for lang in cls]

    @classmethod
    def ids(cls) -> list[str]:
        return [lang.name.lower() for lang in cls]
