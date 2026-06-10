import opencc

from config import DIR_SRT
from language import Language

# Maps each Language to its OpenCC source script code
SCRIPT_FOR_LANGUAGE: dict[Language, str] = {
    Language.MANDARIN_CN: "s",
    Language.MANDARIN_TW: "tw",
}

# OpenCC config per (source_script, target_script).
# Valid paths: s to tw or t  and  tw to s.
_CONFIGS: dict[tuple[str, str], str] = {
    ("s",  "tw"): "s2tw",
    ("s",  "t"):  "s2t",
    ("tw", "s"):  "tw2s",
}

# OpenCC does not convert quotation marks, so we do it manually.
# Simplified mainland uses " " ' ' ; Traditional Taiwan/Chinese uses 「 」 『 』.
_PUNCT_MAP: dict[tuple[str, str], dict[str, str]] = {
    ("s",  "tw"): {"“": "「", "”": "」",  # " " =「 」
                   "‘": "『", "’": "』"},  # ' ' = 『 』
    ("s",  "t"):  {"“": "「", "”": "」",
                   "‘": "『", "’": "』"},
    ("tw", "s"):  {"「": "“", "」": "”",  # 「 」 = " "
                   "『": "‘", "』": "’"},  # 『 』 = ' '
}


def convert_srt_dir(source_script: str, target_script: str) -> None:
    # Convert all SRT files in DIR_SRT from source_script to target_script in-place.
    if source_script == target_script:
        return

    config = _CONFIGS.get((source_script, target_script))
    if config is None:
        raise ValueError(f"No conversion path from {source_script!r} to {target_script!r}")

    converter = opencc.OpenCC(config)
    punct_table = str.maketrans(_PUNCT_MAP.get((source_script, target_script), {}))
    srt_files = sorted(DIR_SRT.glob("*.srt"))
    if not srt_files:
        print("  no SRT files to convert")
        return

    for srt_path in srt_files:
        text = srt_path.read_text(encoding="utf-8")
        text = converter.convert(text).translate(punct_table)
        srt_path.write_text(text, encoding="utf-8")
        print(f"  converted: {srt_path.name}")
