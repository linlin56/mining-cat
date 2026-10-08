import re
from pathlib import Path

import opencc

from config import DIR_SRT
from language import Language

# Maps each Language to its OpenCC source script code
SCRIPT_FOR_LANGUAGE: dict[Language, str] = {
    Language.MANDARIN_CN: "s",
    Language.MANDARIN_TW: "tw",
    Language.CANTONESE_HK: "hk",
    # Taigi isn't converted with OpenCC: "nan" stands for any of its writing systems (mining/taigi.py)
    Language.TAIGI: "nan",
}
TAIGI_TARGETS = ("hanji", "tailo", "poj")

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


def _taigi(source_script: str, target_script: str) -> bool:
    if source_script != "nan":
        return False
    if target_script not in TAIGI_TARGETS:
        raise ValueError(f"No conversion path from {source_script!r} to {target_script!r}")
    return True


def convert_text(text: str, source_script: str, target_script: str) -> str:
    if source_script == target_script:
        return text
    if _taigi(source_script, target_script):
        from mining import taigi
        return taigi.convert(text, target_script)
    config = _CONFIGS.get((source_script, target_script))
    if config is None:
        raise ValueError(f"No conversion path from {source_script!r} to {target_script!r}")

    converter = opencc.OpenCC(config)
    punct_table = str.maketrans(_PUNCT_MAP.get((source_script, target_script), {}))
    return converter.convert(text).translate(punct_table)


# Index and timecode lines of an SRT file: Taigi's conversion leaves them as they are.
_SRT_CUE_LINE = re.compile(r"^\s*(\d+|[\d:,.]+ --> [\d:,.]+.*)\s*$")


def convert_srt_file(srt_path: Path, source_script: str, target_script: str) -> None:
    if source_script == target_script:
        return
    if _taigi(source_script, target_script):
        lines = srt_path.read_text(encoding="utf-8").split("\n")
        converted = [line if _SRT_CUE_LINE.match(line) else convert_text(line, source_script, target_script) for line in lines]
        srt_path.write_text("\n".join(converted), encoding="utf-8")
        return
    text = srt_path.read_text(encoding="utf-8")
    srt_path.write_text(convert_text(text, source_script, target_script), encoding="utf-8")


def convert_srt_dir(source_script: str, target_script: str) -> None:
    # Convert all SRT files in DIR_SRT from source_script to target_script in-place.
    if source_script == target_script:
        return
    if not _taigi(source_script, target_script) and (source_script, target_script) not in _CONFIGS:
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
    # Qwen3-ASR writes Taigi in Chinese characters, often simplified: Hanji are traditional, as in Taiwan.
    canonical = "tw" if language is Language.TAIGI else SCRIPT_FOR_LANGUAGE.get(language)
    if canonical is None or canonical == "s":
        return
    convert_srt_file(srt_path, "s", canonical)
