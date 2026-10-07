import re
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class LangConfig:
    label: str
    whisper_code: str
    iso639_2: str  # ISO 639-2 code used for MP4 subtitle track metadata
    closing_punct: frozenset
    opening_punct: frozenset
    # Regex pattern for in-text vocabulary annotations to strip before alignment.
    vocab_annotation_pattern: str
    ocr_lang_apple: str  # BCP-47 code for Apple Vision's setRecognitionLanguages_
    ocr_lang_easyocr: str  # short code for easyocr.Reader([...])
    # Speech engines, for the languages Whisper doesn't know: 'whisper', or 'qwen3' (Qwen3-ASR, local) to transcribe,
    # 'mms' (CTC forced alignment of the romanized text, local) to align a book on its audiobook.
    asr: str = 'whisper'
    aligner: str = 'whisper'


class Language(Enum):
    MANDARIN_TW = LangConfig(
        label='Mandarin - Taiwan (Traditional)',
        whisper_code='zh',
        iso639_2='zho',
        closing_punct=frozenset('。？！」』'),
        opening_punct=frozenset('「『'),
        vocab_annotation_pattern=r'\[\d+\]',
        ocr_lang_apple='zh-Hant',
        ocr_lang_easyocr='ch_tra',
    )
    MANDARIN_CN = LangConfig(
        label='Mandarin - China (Simplified)',
        whisper_code='zh',
        iso639_2='zho',
        closing_punct=frozenset('。？！」”'),
        opening_punct=frozenset('“'),
        vocab_annotation_pattern=r'\[\d+\]',
        ocr_lang_apple='zh-Hans',
        ocr_lang_easyocr='ch_sim',
    )
    JAPANESE = LangConfig(
        label='Japanese',
        whisper_code='ja',
        iso639_2='jpn',
        closing_punct=frozenset('。？！」』）'),
        opening_punct=frozenset('「『（'),
        vocab_annotation_pattern=r'［＃.+?］',
        ocr_lang_apple='ja-JP',
        ocr_lang_easyocr='ja',
    )
    FRENCH = LangConfig(
        label='French',
        whisper_code='fr',
        iso639_2='fra',
        closing_punct=frozenset('!?»…”’'),
        opening_punct=frozenset('«'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='fr-FR',
        ocr_lang_easyocr='fr',
    )
    ENGLISH_US = LangConfig(
        label='English - United States',
        whisper_code='en',
        iso639_2='eng',
        closing_punct=frozenset('.?!"”’'),
        opening_punct=frozenset('“‘'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='en-US',
        ocr_lang_easyocr='en',
    )
    ENGLISH_UK = LangConfig(
        label='English - United Kingdom',
        whisper_code='en',
        iso639_2='eng',
        closing_punct=frozenset('.?!’”'),
        opening_punct=frozenset('‘“'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='en-GB',
        ocr_lang_easyocr='en',
    )
    ITALIAN = LangConfig(
        label='Italian',
        whisper_code='it',
        iso639_2='ita',
        closing_punct=frozenset('!?»…”'),
        opening_punct=frozenset('«'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='it-IT',
        ocr_lang_easyocr='it',
    )
    SPANISH = LangConfig(
        label='Spanish',
        whisper_code='es',
        iso639_2='spa',
        closing_punct=frozenset('!?»…”'),
        opening_punct=frozenset('«¿¡'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='es-ES',
        ocr_lang_easyocr='es',
    )
    POLISH = LangConfig(
        label='Polish',
        whisper_code='pl',
        iso639_2='pol',
        closing_punct=frozenset('!?…”'),
        opening_punct=frozenset('„'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='pl-PL',
        ocr_lang_easyocr='pl',
    )
    KOREAN = LangConfig(
        label='Korean',
        whisper_code='ko',
        iso639_2='kor',
        closing_punct=frozenset('.?!…”’'),
        opening_punct=frozenset('“‘'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='ko-KR',
        ocr_lang_easyocr='ko',
    )
    GERMAN = LangConfig(
        label='German',
        whisper_code='de',
        iso639_2='deu',
        closing_punct=frozenset('!?…”'),
        opening_punct=frozenset('„'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='de-DE',
        ocr_lang_easyocr='de',
    )
    PORTUGUESE = LangConfig(
        label='Portuguese',
        whisper_code='pt',
        iso639_2='por',
        closing_punct=frozenset('!?»…”'),
        opening_punct=frozenset('«'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='pt-PT',
        ocr_lang_easyocr='pt',
    )
    VIETNAMESE = LangConfig(
        label='Vietnamese',
        whisper_code='vi',
        iso639_2='vie',
        closing_punct=frozenset('.?!…”’'),
        opening_punct=frozenset('“‘'),
        vocab_annotation_pattern=r'',
        ocr_lang_apple='vi-VN',
        ocr_lang_easyocr='vi',
    )
    CANTONESE_HK = LangConfig(
        label='Cantonese - Hong Kong (Traditional)',
        whisper_code='yue',
        iso639_2='yue',
        closing_punct=frozenset('。？！」』'),
        opening_punct=frozenset('「『'),
        vocab_annotation_pattern=r'\[\d+\]',
        ocr_lang_apple='zh-Hant',
        ocr_lang_easyocr='ch_tra',
    )
    # Whisper has no Taigi: Qwen3-ASR transcribes it (in Hanji), and books are aligned on their romanization.
    TAIGI = LangConfig(
        label='Taiwanese Hokkien - Taigi',
        whisper_code='nan',
        iso639_2='nan',
        closing_punct=frozenset('。？！」』.?!”'),
        opening_punct=frozenset('「『“'),
        vocab_annotation_pattern=r'\[\d+\]',
        ocr_lang_apple='zh-Hant',
        ocr_lang_easyocr='ch_tra',
        asr='qwen3',
        aligner='mms',
    )
    # TODO : Add more! Priorities are languages that me (the owner) can understand enough to test

    # BCP-47 tag of a text in the language: the OCR's, except for the Chinese languages that share its zh-Hant.
    @property
    def tag(self) -> str:
        return {'CANTONESE_HK': 'yue-Hant', 'TAIGI': 'nan-Hant'}.get(self.name, self.value.ocr_lang_apple)

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


# A sentence end (a period only before a space or the end: 3.5 isn't one), then its closing quotes or brackets.
_SENTENCE_END = re.compile(r"(?:[。？！?!…]+|\.(?=[\s」』”’\"')）]|$))[」』”’\"')）]*")
_CLAUSE = re.compile(r"[^，,、；;：:]*(?:[，,、；;：:]+|$)")


def split_sentences(text: str, max_chars: int = 80) -> list[str]:
    """The sentences of a text, for engines working sentence by sentence (speech alignment and synthesis): cut after
    the sentence-final punctuation and at line breaks, and a sentence longer than max_chars after its commas."""
    sentences = []
    for line in text.splitlines():
        ends = [m.end() for m in _SENTENCE_END.finditer(line)]
        for start, end in zip([0, *ends], [*ends, len(line)]):
            sentence = line[start:end].strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                sentences.append(sentence)
                continue
            part = ""
            for clause in _CLAUSE.findall(sentence):
                if part and len(part) + len(clause) > max_chars:
                    sentences.append(part.strip())
                    part = ""
                part += clause
            if part.strip():
                sentences.append(part.strip())
    return sentences
