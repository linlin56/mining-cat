import sys
from pathlib import Path

from language import Language

# gui_components/ -> src/ -> project root
ROOT    = Path(__file__).parent.parent.parent
SRC_DIR = Path(__file__).parent.parent

DIR_AUDIOBOOK = ROOT / "sources" / "audiobook"
DIR_EBOOK     = ROOT / "sources" / "ebook"
DIR_FINAL     = ROOT / "output" / "final"

import platform
_VENV_PYTHON = (
    ROOT / ".venv" / "Scripts" / "python.exe"
    if platform.system() == "Windows"
    else ROOT / ".venv" / "bin" / "python3"
)
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable

STEPS = [
    ("Step 1/4 - Audio preparation",  10,  "audio",     []),
    ("Step 2/4 - EPUB extraction",    25,  "epub",      []),
    ("Step 3/4 - Alignment",          40,  "align",     []),
    ("Step 4/4 - MP4 export",         80,  "export",    ["--all"]),
]

STEPS_WHISPER = [
    ("Step 1/3 - Audio preparation",  10,  "audio",      []),
    ("Step 2/3 - Transcription",      40,  "transcribe", []),
    ("Step 3/3 - MP4 export",         80,  "export",     ["--all"]),
]

STEPS_TTS = [
    ("Step 1/3 - EPUB extraction",   10,  "epub",   []),
    ("Step 2/3 - Audio + subtitles", 40,  "tts",    []),
    ("Step 3/3 - MP4 export",        80,  "export", ["--all"]),
]

_CONVERT_OPTIONS_FOR_SCRIPT: dict[str, list[tuple[str, str | None]]] = {
    "s": [
        ("No conversion", None),
        ("Traditional - Taiwan", "tw"),
        ("Traditional - Chinese", "t"),
    ],
    "tw": [
        ("No conversion", None),
        ("Simplified - China", "s"),
    ],
}
CONVERT_BY_LABEL: dict[str, str | None] = {
    label: code
    for options in _CONVERT_OPTIONS_FOR_SCRIPT.values()
    for label, code in options
}

_VOICES_FOR_LANGUAGE: dict[Language, list[tuple[str, str]]] = {
    Language.MANDARIN_TW: [
        ("HsiaoChen - Mandarin (Taiwan), female", "zh-TW-HsiaoChenNeural"),
        ("HsiaoYu - Mandarin (Taiwan), female",   "zh-TW-HsiaoYuNeural"),
        ("YunJhe - Mandarin (Taiwan), male",       "zh-TW-YunJheNeural"),
    ],
    Language.MANDARIN_CN: [
        ("Xiaoxiao - Mandarin (China), female",    "zh-CN-XiaoxiaoNeural"),
        ("Xiaoyi - Mandarin (China), female",      "zh-CN-XiaoyiNeural"),
        ("Yunxi - Mandarin (China), male",         "zh-CN-YunxiNeural"),
        ("Yunjian - Mandarin (China), male",       "zh-CN-YunjianNeural"),
        ("Yunxia - Mandarin (China), male",        "zh-CN-YunxiaNeural"),
        ("Yunyang - Mandarin (China), male",       "zh-CN-YunyangNeural"),
    ],
    Language.JAPANESE: [
        ("Nanami - Japanese, female",  "ja-JP-NanamiNeural"),
        ("Keita - Japanese, male",     "ja-JP-KeitaNeural"),
        ("Mayu - Japanese, female",    "ja-JP-MayuNeural"),
        ("Naoki - Japanese, male",     "ja-JP-NaokiNeural"),
        ("Shiori - Japanese, female",  "ja-JP-ShioriNeural"),
    ],
    Language.FRENCH: [
        ("Denise - French (France), female",  "fr-FR-DeniseNeural"),
        ("Eloise - French (France), female",  "fr-FR-EloiseNeural"),
        ("Henri - French (France), male",     "fr-FR-HenriNeural"),
        ("Sylvie - French (Canada), female",  "fr-CA-SylvieNeural"),
        ("Jean - French (Canada), male",      "fr-CA-JeanNeural"),
    ],
    Language.ENGLISH_US: [
        ("Jenny - English (US), female",    "en-US-JennyNeural"),
        ("Aria - English (US), female",     "en-US-AriaNeural"),
        ("Michelle - English (US), female", "en-US-MichelleNeural"),
        ("Guy - English (US), male",        "en-US-GuyNeural"),
        ("Eric - English (US), male",       "en-US-EricNeural"),
        ("Roger - English (US), male",      "en-US-RogerNeural"),
    ],
    Language.ENGLISH_UK: [
        ("Sonia - English (UK), female",  "en-GB-SoniaNeural"),
        ("Libby - English (UK), female",  "en-GB-LibbyNeural"),
        ("Maisie - English (UK), female", "en-GB-MaisieNeural"),
        ("Ryan - English (UK), male",     "en-GB-RyanNeural"),
        ("Oliver - English (UK), male",   "en-GB-OliverNeural"),
        ("Thomas - English (UK), male",   "en-GB-ThomasNeural"),
    ],
}
DEFAULT_VOICE_FOR_LANGUAGE: dict[Language, str] = {
    Language.MANDARIN_TW: "HsiaoChen - Mandarin (Taiwan), female",
    Language.MANDARIN_CN: "Xiaoxiao - Mandarin (China), female",
    Language.JAPANESE:    "Nanami - Japanese, female",
    Language.FRENCH:      "Denise - French (France), female",
    Language.ENGLISH_US:  "Jenny - English (US), female",
    Language.ENGLISH_UK:  "Sonia - English (UK), female",
}
VOICE_ID_BY_LABEL: dict[str, str] = {
    label: voice_id
    for voices in _VOICES_FOR_LANGUAGE.values()
    for label, voice_id in voices
}
VOICES_FOR_LANGUAGE = _VOICES_FOR_LANGUAGE

GITHUB_URL = "https://github.com/linlin56/audiobook-miner"
