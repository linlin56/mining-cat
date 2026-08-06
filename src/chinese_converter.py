from pathlib import Path

import opencc

from config import DIR_SRT
from language import Language

# Maps each Language to its OpenCC source script code
SCRIPT_FOR_LANGUAGE: dict[Language, str] = {
    Language.MANDARIN_CN: "s",
    Language.MANDARIN_TW: "tw",
    Language.CANTONESE_HK: "hk",
}

# OpenCC config per (source_script, target_script).
# Valid paths: s to tw, t or hk  and  tw to s  and  hk to s.
_CONFIGS: dict[tuple[str, str], str] = {
    ("s",  "tw"): "s2tw",
    ("s",  "t"):  "s2t",
    ("s",  "hk"): "s2hk",
    ("tw", "s"):  "tw2s",
    ("hk", "s"):  "hk2s",
}

# OpenCC does not convert quotation marks, so we do it manually.
# Simplified mainland uses " " ' ' ; Traditional Taiwan/Chinese/HK uses 「 」 『 』.
_PUNCT_MAP: dict[tuple[str, str], dict[str, str]] = {
    ("s",  "tw"): {"“": "「", "”": "」",  # " " =「 」
                   "‘": "『", "’": "』"},  # ' ' = 『 』
    ("s",  "t"):  {"“": "「", "”": "」",
                   "‘": "『", "’": "』"},
    ("s",  "hk"): {"“": "「", "”": "」",
                   "‘": "『", "’": "』"},
    ("tw", "s"):  {"「": "“", "」": "”",  # 「 」 = " "
                   "『": "‘", "』": "’"},  # 『 』 = ' '
    ("hk", "s"):  {"「": "“", "」": "”",
                   "『": "‘", "』": "’"},
}


def convert_srt_file(srt_path: Path, source_script: str, target_script: str) -> None:
    if source_script == target_script:
        return
    config = _CONFIGS.get((source_script, target_script))
    if config is None:
        raise ValueError(f"No conversion path from {source_script!r} to {target_script!r}")

    converter = opencc.OpenCC(config)
    punct_table = str.maketrans(_PUNCT_MAP.get((source_script, target_script), {}))
    text = srt_path.read_text(encoding="utf-8")
    text = converter.convert(text).translate(punct_table)
    srt_path.write_text(text, encoding="utf-8")


def convert_srt_dir(source_script: str, target_script: str) -> None:
    # Convert all SRT files in DIR_SRT from source_script to target_script in-place.
    if source_script == target_script:
        return
    if (source_script, target_script) not in _CONFIGS:
        raise ValueError(f"No conversion path from {source_script!r} to {target_script!r}")

    srt_files = sorted(DIR_SRT.glob("*.srt"))
    if not srt_files:
        print("  no SRT files to convert")
        return

    for srt_path in srt_files:
        convert_srt_file(srt_path, source_script, target_script)
        print(f"  converted: {srt_path.name}")


# Whisper's free transcription of Chinese-family languages is inconsistently scripted -
# it often defaults to Simplified regardless of dialect, since there's no reference text
# to anchor the script (unlike forced alignment against an EPUB chapter, whose script is
# whatever the source book already uses). This normalizes freshly-transcribed SRTs to the
# language's expected script before any user-requested --convert-to runs on top of it.
# OpenCC's s2* conversions are idempotent on text that's already in the target script, so
# this is safe to call even when Whisper's output happened to already be correct.
def normalize_whisper_script(srt_path: Path, language: Language) -> None:
    canonical = SCRIPT_FOR_LANGUAGE.get(language)
    if canonical is None or canonical == "s":
        return
    convert_srt_file(srt_path, "s", canonical)
