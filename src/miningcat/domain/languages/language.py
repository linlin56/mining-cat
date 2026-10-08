from enum import Enum

from miningcat.domain.languages.profile import LanguageProfile, SpeechEngine, WordSegmentation
from miningcat.domain.languages.profile_builder import LanguageProfileBuilder
from miningcat.domain.languages.tags import language_key
from miningcat.domain.text import scripts


class Language(Enum):
    """The language variants of the converter, the OCR and the video game capture. Each member holds its
    LanguageProfile: adding a language means adding a member here (see docs/how-to-contribute/add-language.md)."""

    MANDARIN_TW = (
        LanguageProfileBuilder("Mandarin - Taiwan (Traditional)")
        .codes(key="zh", whisper="zh", iso639_2="zho")
        .punctuation(closing="。？！」』", opening="「『")
        .vocab_annotations(r"\[\d+\]")
        .ocr(apple="zh-Hant", easyocr="ch_tra", script=scripts.CJK)
        .voices(
            ("HsiaoChen - Mandarin (Taiwan), female", "zh-TW-HsiaoChenNeural"),
            ("HsiaoYu - Mandarin (Taiwan), female", "zh-TW-HsiaoYuNeural"),
            ("YunJhe - Mandarin (Taiwan), male", "zh-TW-YunJheNeural"),
        )
        .youtube_captions("zh-Hant", "zh-TW", "zh")
        .script("tw")
        .word_segmentation(WordSegmentation.CHINESE)
        .character_list("zh-Hant", scripts.HAN)
        .build()
    )
    MANDARIN_CN = (
        LanguageProfileBuilder("Mandarin - China (Simplified)")
        .codes(key="zh", whisper="zh", iso639_2="zho")
        .punctuation(closing="。？！」”", opening="“")
        .vocab_annotations(r"\[\d+\]")
        .ocr(apple="zh-Hans", easyocr="ch_sim", script=scripts.CJK)
        .voices(
            ("Xiaoxiao - Mandarin (China), female", "zh-CN-XiaoxiaoNeural"),
            ("Xiaoyi - Mandarin (China), female", "zh-CN-XiaoyiNeural"),
            ("Yunxi - Mandarin (China), male", "zh-CN-YunxiNeural"),
            ("Yunjian - Mandarin (China), male", "zh-CN-YunjianNeural"),
            ("Yunxia - Mandarin (China), male", "zh-CN-YunxiaNeural"),
            ("Yunyang - Mandarin (China), male", "zh-CN-YunyangNeural"),
        )
        .youtube_captions("zh-Hans", "zh-CN", "zh")
        .script("s")
        .word_segmentation(WordSegmentation.CHINESE)
        .character_list("zh-Hans", scripts.HAN)
        .build()
    )
    JAPANESE = (
        LanguageProfileBuilder("Japanese")
        .codes(key="ja", whisper="ja", iso639_2="jpn")
        .punctuation(closing="。？！」』）", opening="「『（")
        .vocab_annotations(r"［＃.+?］")
        .ocr(apple="ja-JP", easyocr="ja", script=scripts.CJK)
        .voices(
            ("Nanami - Japanese, female", "ja-JP-NanamiNeural"),
            ("Keita - Japanese, male", "ja-JP-KeitaNeural"),
            ("Mayu - Japanese, female", "ja-JP-MayuNeural"),
            ("Naoki - Japanese, male", "ja-JP-NaokiNeural"),
            ("Shiori - Japanese, female", "ja-JP-ShioriNeural"),
        )
        .word_segmentation(WordSegmentation.JAPANESE)
        .character_list("ja", scripts.HAN_AND_KANA)
        .build()
    )
    FRENCH = (
        LanguageProfileBuilder("French")
        .codes(key="fr", whisper="fr", iso639_2="fra")
        .punctuation(closing="!?»…”’", opening="«")
        .ocr(apple="fr-FR", easyocr="fr")
        .voices(
            ("Denise - French (France), female", "fr-FR-DeniseNeural"),
            ("Eloise - French (France), female", "fr-FR-EloiseNeural"),
            ("Henri - French (France), male", "fr-FR-HenriNeural"),
            ("Sylvie - French (Canada), female", "fr-CA-SylvieNeural"),
            ("Jean - French (Canada), male", "fr-CA-JeanNeural"),
        )
        .build()
    )
    ENGLISH_US = (
        LanguageProfileBuilder("English - United States")
        .codes(key="en", whisper="en", iso639_2="eng")
        .punctuation(closing='.?!"”’', opening="“‘")
        .ocr(apple="en-US", easyocr="en")
        .voices(
            ("Jenny - English (US), female", "en-US-JennyNeural"),
            ("Aria - English (US), female", "en-US-AriaNeural"),
            ("Michelle - English (US), female", "en-US-MichelleNeural"),
            ("Guy - English (US), male", "en-US-GuyNeural"),
            ("Eric - English (US), male", "en-US-EricNeural"),
            ("Roger - English (US), male", "en-US-RogerNeural"),
        )
        .build()
    )
    ENGLISH_UK = (
        LanguageProfileBuilder("English - United Kingdom")
        .codes(key="en", whisper="en", iso639_2="eng")
        .punctuation(closing=".?!’”", opening="‘“")
        .ocr(apple="en-GB", easyocr="en")
        .voices(
            ("Sonia - English (UK), female", "en-GB-SoniaNeural"),
            ("Libby - English (UK), female", "en-GB-LibbyNeural"),
            ("Maisie - English (UK), female", "en-GB-MaisieNeural"),
            ("Ryan - English (UK), male", "en-GB-RyanNeural"),
            ("Oliver - English (UK), male", "en-GB-OliverNeural"),
            ("Thomas - English (UK), male", "en-GB-ThomasNeural"),
        )
        .youtube_captions("en-GB", "en")
        .build()
    )
    ITALIAN = (
        LanguageProfileBuilder("Italian")
        .codes(key="it", whisper="it", iso639_2="ita")
        .punctuation(closing="!?»…”", opening="«")
        .ocr(apple="it-IT", easyocr="it")
        .voices(
            ("Elsa - Italian, female", "it-IT-ElsaNeural"),
            ("Isabella - Italian, female", "it-IT-IsabellaNeural"),
            ("Diego - Italian, male", "it-IT-DiegoNeural"),
            ("Benigno - Italian, male", "it-IT-BenignoNeural"),
        )
        .build()
    )
    SPANISH = (
        LanguageProfileBuilder("Spanish")
        .codes(key="es", whisper="es", iso639_2="spa")
        .punctuation(closing="!?»…”", opening="«¿¡")
        .ocr(apple="es-ES", easyocr="es")
        .voices(
            ("Elvira - Spanish (Spain), female", "es-ES-ElviraNeural"),
            ("Alvaro - Spanish (Spain), male", "es-ES-AlvaroNeural"),
            ("Dalia - Spanish (Mexico), female", "es-MX-DaliaNeural"),
            ("Jorge - Spanish (Mexico), male", "es-MX-JorgeNeural"),
        )
        .build()
    )
    POLISH = (
        LanguageProfileBuilder("Polish")
        .codes(key="pl", whisper="pl", iso639_2="pol")
        .punctuation(closing="!?…”", opening="„")
        .ocr(apple="pl-PL", easyocr="pl")
        .voices(
            ("Zofia - Polish, female", "pl-PL-ZofiaNeural"),
            ("Marek - Polish, male", "pl-PL-MarekNeural"),
        )
        .build()
    )
    KOREAN = (
        LanguageProfileBuilder("Korean")
        .codes(key="ko", whisper="ko", iso639_2="kor")
        .punctuation(closing=".?!…”’", opening="“‘")
        .ocr(apple="ko-KR", easyocr="ko", script=scripts.HANGUL)
        .voices(
            ("SunHi - Korean, female", "ko-KR-SunHiNeural"),
            ("InJoon - Korean, male", "ko-KR-InJoonNeural"),
        )
        .build()
    )
    GERMAN = (
        LanguageProfileBuilder("German")
        .codes(key="de", whisper="de", iso639_2="deu")
        .punctuation(closing="!?…”", opening="„")
        .ocr(apple="de-DE", easyocr="de")
        .voices(
            ("Katja - German, female", "de-DE-KatjaNeural"),
            ("Amala - German, female", "de-DE-AmalaNeural"),
            ("Conrad - German, male", "de-DE-ConradNeural"),
            ("Killian - German, male", "de-DE-KillianNeural"),
        )
        .build()
    )
    PORTUGUESE = (
        LanguageProfileBuilder("Portuguese")
        .codes(key="pt", whisper="pt", iso639_2="por")
        .punctuation(closing="!?»…”", opening="«")
        .ocr(apple="pt-PT", easyocr="pt")
        .voices(
            ("Francisca - Portuguese (Brazil), female", "pt-BR-FranciscaNeural"),
            ("Antonio - Portuguese (Brazil), male", "pt-BR-AntonioNeural"),
            ("Raquel - Portuguese (Portugal), female", "pt-PT-RaquelNeural"),
            ("Duarte - Portuguese (Portugal), male", "pt-PT-DuarteNeural"),
        )
        .youtube_captions("pt-PT", "pt-BR", "pt")
        .build()
    )
    VIETNAMESE = (
        LanguageProfileBuilder("Vietnamese")
        .codes(key="vi", whisper="vi", iso639_2="vie")
        .punctuation(closing=".?!…”’", opening="“‘")
        .ocr(apple="vi-VN", easyocr="vi")
        .voices(
            ("HoaiMy - Vietnamese, female", "vi-VN-HoaiMyNeural"),
            ("NamMinh - Vietnamese, male", "vi-VN-NamMinhNeural"),
        )
        .build()
    )
    CANTONESE_HK = (
        LanguageProfileBuilder("Cantonese - Hong Kong (Traditional)")
        .codes(key="yue", whisper="yue", iso639_2="yue", tag="yue-Hant")
        .punctuation(closing="。？！」』", opening="「『")
        .vocab_annotations(r"\[\d+\]")
        .ocr(apple="zh-Hant", easyocr="ch_tra", script=scripts.CJK)
        .voices(
            ("HiuMaan - Cantonese (Hong Kong), female", "zh-HK-HiuMaanNeural"),
            ("HiuGaai - Cantonese (Hong Kong), female", "zh-HK-HiuGaaiNeural"),
            ("WanLung - Cantonese (Hong Kong), male", "zh-HK-WanLungNeural"),
        )
        .youtube_captions("yue", "zh-HK", "zh-Hant", "zh")
        .script("hk")
        .large_whisper_models_only()
        .build()
    )
    # Whisper has no Taigi: Qwen3-ASR transcribes it (in Hanji), and books are aligned on their romanization.
    TAIGI = (
        LanguageProfileBuilder("Taiwanese Hokkien - Taigi")
        .codes(key="nan", whisper="nan", iso639_2="nan", tag="nan-Hant")
        .punctuation(closing="。？！」』.?!”", opening="「『“")
        .vocab_annotations(r"\[\d+\]")
        .ocr(apple="zh-Hant", easyocr="ch_tra", script=scripts.HAN_OR_LATIN)
        # Vietnamese: the Latin model with the most diacritics (Tâi-lô's and POJ's come back as look-alikes,
        # see domain/text/taigi/ocr_repair.py).
        .latin_ocr(apple="vi-VT", easyocr="vi")
        # Edge has no Taigi voice: Meta's MMS voice runs locally (infrastructure/speech/mms_tts.py).
        .voices(("MMS - Taigi (local, Meta MMS-TTS)", "nan-TW-MmsTaigi"))
        .youtube_captions("nan", "nan-TW", "zh-min-nan", "zh-TW", "zh-Hant")
        .script("nan")
        .speech(transcriber=SpeechEngine.QWEN3_ASR, aligner=SpeechEngine.MMS)
        .word_segmentation(WordSegmentation.TAIGI)
        .character_list("zh-Hant", scripts.HAN)
        .build()
    )
    # TODO : Add more! Priorities are languages that me (the owner) can understand enough to test

    @property
    def profile(self) -> LanguageProfile:
        return self.value

    @property
    def id(self) -> str:
        """The id used by the CLI and the web API: "mandarin_tw"."""
        return self.name.lower()

    @classmethod
    def from_id(cls, lang_id: str) -> "Language":
        for lang in cls:
            if lang.id == lang_id.lower():
                return lang
        raise ValueError(f"Unknown language id: {lang_id!r}")

    @classmethod
    def from_label(cls, label: str) -> "Language":
        for lang in cls:
            if lang.profile.label == label:
                return lang
        raise ValueError(f"Unknown language label: {label!r}")

    @classmethod
    def all_labels(cls) -> list[str]:
        return [lang.profile.label for lang in cls]

    @classmethod
    def ids(cls) -> list[str]:
        return [lang.id for lang in cls]

    @classmethod
    def variants_of(cls, key: str) -> list["Language"]:
        """The variants of a study language: Mandarin is Taiwan or China."""
        return [lang for lang in cls if lang.profile.key == key]

    @classmethod
    def for_tag(cls, tag: str | None) -> "Language | None":
        """The variant a text tagged `tag` is written in: zh-Hans is Mandarin in simplified characters."""
        tag = (tag or "").lower()
        variants = cls.variants_of(language_key(tag))
        if not variants:
            return None
        for lang in variants:
            if lang.profile.ocr_lang_apple.lower() == tag:
                return lang
        if language_key(tag) == "zh" and "hans" in tag:
            return cls.MANDARIN_CN
        return variants[0]
