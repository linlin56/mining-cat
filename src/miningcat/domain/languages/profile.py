import re
from dataclasses import dataclass
from enum import Enum


class WordSegmentation(Enum):
    """How a text is split into words for a word frequency list."""

    SPACES = "spaces"        # words are separated by spaces and punctuation
    CHINESE = "chinese"      # jieba
    JAPANESE = "japanese"    # janome
    TAIGI = "taigi"          # taibun's Hanji words, and romanized words


class SpeechEngine(Enum):
    """What transcribes a language, or aligns a book on its audiobook. Whisper by default; local models for the
    languages it doesn't know."""

    WHISPER = "whisper"
    QWEN3_ASR = "qwen3"    # Qwen3-ASR transcribes Taigi (in Hanji)
    MMS = "mms"            # Meta's MMS aligner: CTC forced alignment of the romanized text


@dataclass(frozen=True)
class Voice:
    """An edge-tts voice, or a local one (Meta's MMS voices, see infrastructure/speech/mms_tts.py)."""

    label: str
    voice_id: str


@dataclass(frozen=True)
class CharacterList:
    """A Kanji Grid character list: its language tag, and the characters it counts."""

    tag: str
    characters: re.Pattern


@dataclass(frozen=True)
class LatinOcr:
    """The OCR languages reading the Latin lines of a language: Apple Vision's BCP-47 code, and EasyOCR's."""

    apple: str
    easyocr: str


@dataclass(frozen=True)
class LanguageProfile:
    """Everything the converter, the OCR and the downloads need to know about one language variant.

    Build one with `LanguageProfileBuilder`: most fields have sensible defaults.
    """

    # Displayed in the dropdowns. Languages with several standards name the region.
    label: str
    # Study language it belongs to ("zh", "yue", "ja"...), see study_language.py.
    key: str
    # BCP-47 tag of texts in this variant (dictionary popup, fonts...).
    tag: str
    whisper_code: str
    # Three-letter code of the MP4 subtitle track metadata.
    iso639_2: str
    # Whisper sometimes puts sentence-final punctuation at the start of the next segment, and loses opening marks.
    closing_punct: frozenset[str]
    opening_punct: frozenset[str]
    # Vocabulary or ruby annotations embedded in ebooks, stripped before alignment ("" when unused).
    vocab_annotation_pattern: str
    # BCP-47 code for Apple Vision, and the EasyOCR code.
    ocr_lang_apple: str
    ocr_lang_easyocr: str
    # Text read by OCR without a single character of this script is noise.
    ocr_script: re.Pattern
    # OCR languages for the lines of a language also written in Latin letters (Taigi's romanizations): their tone
    # marks are lost by the CJK model, a Latin one sees them. None: the language's own OCR reads everything.
    latin_ocr: LatinOcr | None
    voices: tuple[Voice, ...]
    # YouTube caption codes to try, in order of preference.
    youtube_caption_codes: tuple[str, ...]
    # The script its subtitles are converted from: OpenCC's "s" (simplified), "tw" (Taiwan) or "hk" (Hong Kong) for
    # Chinese variants, "nan" for Taigi (any of its writing systems, see domain/text/taigi). None: no conversion.
    script: str | None
    # Whisper only knows a few languages (like Cantonese) with its large-v3 and turbo checkpoints.
    large_whisper_models_only: bool
    transcriber: SpeechEngine
    aligner: SpeechEngine
    word_segmentation: WordSegmentation
    character_list: CharacterList | None

    @property
    def default_voice(self) -> Voice | None:
        return self.voices[0] if self.voices else None

    def voice_id(self, label: str) -> str | None:
        return next((v.voice_id for v in self.voices if v.label == label), None)
