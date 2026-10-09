"""ASCII punctuation in Chinese and Japanese text replaced by the script's own: 你好,我是 → 你好，我是.

Only the punctuation that follows a character of the script is replaced (with the spaces around it): numbers (3.5),
English words and romanized Taigi keep theirs."""
import re

from miningcat.domain.languages.tags import language_key

# Han, kana, bopomofo and full-width punctuation: what a replaced mark follows.
_SCRIPT = re.compile(r"[　-〿぀-ヿ㄀-ㄯ㐀-䶿一-鿿豈-﫿！-｠]")
_HAN_OR_KANA = re.compile(r"[぀-ヿ㄀-ㄯ㐀-䶿一-鿿豈-﫿]")

_CHINESE = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}
_JAPANESE = {**_CHINESE, ",": "、"}
_SIMPLIFIED = ("zh-hans", "zh-cn", "zh-sg", "zh-my")


def _style(tag: str) -> tuple[dict, str, tuple[str, str]] | None:
    """The marks, the ellipsis and the quotes of a language tag; None when its script has no punctuation of its own."""
    key = language_key(tag)
    if key == "ja":
        return _JAPANESE, "…", ("「", "」")
    if key in ("zh", "yue", "nan"):
        simplified = (tag or "").lower().startswith(_SIMPLIFIED)
        return _CHINESE, "……", ("“", "”") if simplified else ("「", "」")
    return None


def _marks(text: str, marks: dict, ellipsis: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        dots = len(text) - i - len(text[i:].lstrip("."))
        is_mark = ch in marks or dots >= 3
        before = "".join(out).rstrip(" ")
        # after a closing ” (simplified Chinese), what it closes
        last = before.rstrip("”’")[-1:]
        if is_mark and last and _SCRIPT.match(last):
            out[:] = [before]
            if dots >= 3:
                out.append(ellipsis)
                i += dots
            else:
                out.append(marks[ch])
                i += 1
            # the spaces after it, unless a Latin word follows
            rest = text[i:].lstrip(" ")
            if not rest or _SCRIPT.match(rest[0]):
                i = len(text) - len(rest)
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _quotes(text: str, quotes: tuple[str, str]) -> str:
    """Straight double quotes in pairs, around Chinese or Japanese text."""
    return re.sub(r'"([^"]*)"', lambda m: f"{quotes[0]}{m.group(1).strip()}{quotes[1]}"
                  if _HAN_OR_KANA.search(m.group(1)) else m.group(0), text)


def _brackets(text: str) -> str:
    return re.sub(r"\s*\(([^()]*)\)\s*", lambda m: f"（{m.group(1).strip()}）"
                  if _HAN_OR_KANA.search(m.group(1)) else m.group(0), text)


def fullwidth_punctuation(text: str, tag: str) -> str:
    """The text with the punctuation of the language of `tag` (zh-Hant: ，。！？「」, zh-Hans: “”, ja: 、。)."""
    style = _style(tag)
    if not style or not _HAN_OR_KANA.search(text):
        return text
    marks, ellipsis, quotes = style
    return _marks(_brackets(_quotes(text, quotes)), marks, ellipsis)
