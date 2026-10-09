import re
from typing import Self

from miningcat.domain.languages.profile import (
    CharacterList,
    LanguageProfile,
    LatinOcr,
    SpeechEngine,
    Voice,
    WordSegmentation,
)
from miningcat.domain.text import scripts


class LanguageProfileBuilder:
    """Builds a LanguageProfile step by step, each language only stating what differs from the defaults:

        LanguageProfileBuilder("Japanese")
            .codes(key="ja", whisper="ja", iso639_2="jpn")
            .punctuation(closing="。？！」』）", opening="「『（")
            .ocr(apple="ja-JP", easyocr="ja", script=scripts.CJK)
            .voices(("Nanami - Japanese, female", "ja-JP-NanamiNeural"))
            .build()
    """

    def __init__(self, label: str):
        self._label = label
        self._key: str | None = None
        self._tag: str | None = None
        self._whisper_code: str | None = None
        self._iso639_2: str | None = None
        self._closing_punct = frozenset()
        self._opening_punct = frozenset()
        self._vocab_annotation_pattern = ""
        self._ocr_lang_apple: str | None = None
        self._ocr_lang_easyocr: str | None = None
        self._ocr_script = scripts.LATIN_LETTER
        self._latin_ocr: LatinOcr | None = None
        self._voices: tuple[Voice, ...] = ()
        self._youtube_caption_codes: tuple[str, ...] = ()
        self._script: str | None = None
        self._large_whisper_models_only = False
        self._transcriber = SpeechEngine.WHISPER
        self._aligner = SpeechEngine.WHISPER
        self._word_segmentation = WordSegmentation.SPACES
        self._character_list: CharacterList | None = None

    def codes(self, *, key: str, whisper: str, iso639_2: str, tag: str | None = None) -> Self:
        """The study language key, the Whisper code, the ISO 639-2 code, and the BCP-47 tag when it isn't the
        Apple OCR code."""
        self._key, self._whisper_code, self._iso639_2, self._tag = key, whisper, iso639_2, tag
        return self

    def punctuation(self, *, closing: str, opening: str = "") -> Self:
        self._closing_punct, self._opening_punct = frozenset(closing), frozenset(opening)
        return self

    def vocab_annotations(self, pattern: str) -> Self:
        self._vocab_annotation_pattern = pattern
        return self

    def ocr(self, *, apple: str, easyocr: str, script: re.Pattern = scripts.LATIN_LETTER) -> Self:
        self._ocr_lang_apple, self._ocr_lang_easyocr, self._ocr_script = apple, easyocr, script
        return self

    def latin_ocr(self, *, apple: str, easyocr: str) -> Self:
        """OCR languages for the lines written in Latin letters, read again by a Latin model."""
        self._latin_ocr = LatinOcr(apple, easyocr)
        return self

    def voices(self, *voices: tuple[str, str]) -> Self:
        """(label, voice id) pairs, the default voice first."""
        self._voices = tuple(Voice(label, voice_id) for label, voice_id in voices)
        return self

    def youtube_captions(self, *codes: str) -> Self:
        self._youtube_caption_codes = codes
        return self

    def script(self, script: str) -> Self:
        """The script its subtitles are converted from: "s", "tw" or "hk" (OpenCC), "nan" (Taigi)."""
        self._script = script
        return self

    def speech(self, *, transcriber: SpeechEngine = SpeechEngine.WHISPER,
               aligner: SpeechEngine = SpeechEngine.WHISPER) -> Self:
        """The engines of a language Whisper doesn't know."""
        self._transcriber, self._aligner = transcriber, aligner
        return self

    def large_whisper_models_only(self) -> Self:
        self._large_whisper_models_only = True
        return self

    def word_segmentation(self, segmentation: WordSegmentation) -> Self:
        self._word_segmentation = segmentation
        return self

    def character_list(self, tag: str, characters: re.Pattern) -> Self:
        self._character_list = CharacterList(tag, characters)
        return self

    def build(self) -> LanguageProfile:
        missing = [name for name, value in (("codes", self._key), ("ocr", self._ocr_lang_apple)) if value is None]
        if missing:
            raise ValueError(f"{self._label}: {', '.join(missing)} not set")
        return LanguageProfile(
            label=self._label,
            key=self._key,
            tag=self._tag or self._ocr_lang_apple,
            whisper_code=self._whisper_code,
            iso639_2=self._iso639_2,
            closing_punct=self._closing_punct,
            opening_punct=self._opening_punct,
            vocab_annotation_pattern=self._vocab_annotation_pattern,
            ocr_lang_apple=self._ocr_lang_apple,
            ocr_lang_easyocr=self._ocr_lang_easyocr,
            ocr_script=self._ocr_script,
            latin_ocr=self._latin_ocr,
            voices=self._voices,
            youtube_caption_codes=self._youtube_caption_codes or (self._whisper_code,),
            script=self._script,
            large_whisper_models_only=self._large_whisper_models_only,
            transcriber=self._transcriber,
            aligner=self._aligner,
            word_segmentation=self._word_segmentation,
            character_list=self._character_list,
        )
