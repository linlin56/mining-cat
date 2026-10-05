import re
import unicodedata

_INITIALS = {
    "b": "ㄅ", "p": "ㄆ", "m": "ㄇ", "f": "ㄈ", "d": "ㄉ", "t": "ㄊ", "n": "ㄋ", "l": "ㄌ",
    "g": "ㄍ", "k": "ㄎ", "h": "ㄏ", "j": "ㄐ", "q": "ㄑ", "x": "ㄒ",
    "zh": "ㄓ", "ch": "ㄔ", "sh": "ㄕ", "r": "ㄖ", "z": "ㄗ", "c": "ㄘ", "s": "ㄙ",
}
_FINALS = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ê": "ㄝ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ", "ou": "ㄡ",
    "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ", "ong": "ㄨㄥ", "er": "ㄦ",
    "i": "ㄧ", "ia": "ㄧㄚ", "io": "ㄧㄛ", "ie": "ㄧㄝ", "iai": "ㄧㄞ", "iao": "ㄧㄠ", "iu": "ㄧㄡ", "ian": "ㄧㄢ",
    "in": "ㄧㄣ", "iang": "ㄧㄤ", "ing": "ㄧㄥ", "iong": "ㄩㄥ",
    "u": "ㄨ", "ua": "ㄨㄚ", "uo": "ㄨㄛ", "uai": "ㄨㄞ", "ui": "ㄨㄟ", "uan": "ㄨㄢ", "un": "ㄨㄣ",
    "uang": "ㄨㄤ", "ueng": "ㄨㄥ",
    "ü": "ㄩ", "üe": "ㄩㄝ", "üan": "ㄩㄢ", "ün": "ㄩㄣ",
}
# Syllables without an initial are spelled with y / w.
_ZERO_INITIAL = {
    "yi": "ㄧ", "ya": "ㄧㄚ", "yo": "ㄧㄛ", "ye": "ㄧㄝ", "yai": "ㄧㄞ", "yao": "ㄧㄠ", "you": "ㄧㄡ", "yan": "ㄧㄢ",
    "yin": "ㄧㄣ", "yang": "ㄧㄤ", "ying": "ㄧㄥ", "yong": "ㄩㄥ",
    "yu": "ㄩ", "yue": "ㄩㄝ", "yuan": "ㄩㄢ", "yun": "ㄩㄣ",
    "wu": "ㄨ", "wa": "ㄨㄚ", "wo": "ㄨㄛ", "wai": "ㄨㄞ", "wei": "ㄨㄟ", "wan": "ㄨㄢ", "wen": "ㄨㄣ",
    "wang": "ㄨㄤ", "weng": "ㄨㄥ",
}
# zhi, chi, shi, ri, zi, ci, si: the initial alone.
_BARE = {"zh", "ch", "sh", "r", "z", "c", "s"}
_TONE_MARKS = {"ˉ": 1, "ˊ": 2, "ˇ": 3, "ˋ": 4}
_COMBINING_TONES = {"̄": 1, "́": 2, "̌": 3, "̀": 4}
_ZHUYIN_TONES = {1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ", 5: "˙"}
_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _build_syllables() -> dict[str, str]:
    table = dict(_ZERO_INITIAL)
    for final, zh in _FINALS.items():
        if not final.startswith(("i", "u", "ü")) or final in ("i",):
            table.setdefault(final, zh)  # a, ai, an, e, er, o, ou... alone
    for initial, zi in _INITIALS.items():
        if initial in _BARE:
            table[initial + "i"] = zi
        for final, zf in _FINALS.items():
            if final == "i" and initial in _BARE:
                continue
            if initial in ("j", "q", "x"):
                # j, q, x are followed by ü, written u
                if final.startswith("ü"):
                    table[initial + "u" + final[1:]] = zi + zf
                elif final.startswith("i"):
                    table[initial + final] = zi + zf
                continue
            if final.startswith("ü"):
                if initial in ("n", "l"):
                    table[initial + final] = zi + zf
                    table[initial + "v" + final[1:]] = zi + zf
                continue
            table[initial + final] = zi + zf
    table.pop("i", None)
    return table


_SYLLABLES = _build_syllables()
_MAX_SYLLABLE = max(len(s) for s in _SYLLABLES)


# Plain letters and the tone of a pinyin chunk: "zhōng" -> ("zhong", 1), "lü4" -> ("lü", 4).
def _plain(text: str) -> tuple[str, int]:
    tone = 0
    letters = []
    for ch in unicodedata.normalize("NFD", text):
        if ch in _COMBINING_TONES:
            tone = _COMBINING_TONES[ch]
        elif ch == "̈":  # diaeresis: ü
            if letters and letters[-1] == "u":
                letters[-1] = "ü"
        else:
            letters.append(ch)
    return unicodedata.normalize("NFC", "".join(letters)), tone


# Splits run-together pinyin into `count` syllables (or as few as possible), each with at most one tone mark.
def _split(word: str, count: int | None) -> list[str] | None:
    n = len(word)
    memo: dict[tuple[int, int | None], list[str] | None] = {}

    def solve(i: int, left: int | None) -> list[str] | None:
        if i == n:
            return [] if left in (None, 0) else None
        if left == 0:
            return None
        key = (i, left)
        if key in memo:
            return memo[key]
        best = None
        for j in range(min(n, i + _MAX_SYLLABLE + 2), i, -1):
            chunk = word[i:j]
            plain, _ = _plain(chunk)
            marks = sum(1 for ch in unicodedata.normalize("NFD", chunk) if ch in _COMBINING_TONES)
            # erhua: a syllable followed by a lone r (huàr)
            if plain not in _SYLLABLES and not (plain == "r" and i > 0) or marks > 1:
                continue
            rest = solve(j, None if left is None else left - 1)
            if rest is not None and (best is None or (left is None and len(rest) + 1 < len(best))):
                best = [chunk] + rest
                if left is not None:
                    break
        memo[key] = best
        return best

    return solve(0, count)


def _syllable(chunk: str, tone: int) -> str:
    plain, mark = _plain(chunk)
    tone = tone or mark or 5
    if plain == "r":
        return "ㄦ"
    zhuyin = _SYLLABLES[plain]
    return ("˙" + zhuyin) if tone == 5 else zhuyin + _ZHUYIN_TONES[tone]


def pinyin_to_zhuyin(pinyin: str, word: str = "") -> str:
    """Zhuyin of a pinyin reading, syllables separated by spaces; "" when it isn't pinyin.
    `word` (the Chinese word) tells how many syllables run-together pinyin has."""
    text = unicodedata.normalize("NFC", (pinyin or "").strip().lower()).replace("u:", "ü").replace("v", "ü")
    if not text:
        return ""
    if re.search(r"[㄀-ㄯ]", text):
        return text  # already zhuyin
    # CC-CEDICT writes erhua with a neutral tone number inside marked pinyin (yīxiàr5): a syllable ending
    text = re.sub(r"(?<=[^\s\d])r5", "r ", text).strip()
    count = len(_HAN.findall(word)) or None
    out = []
    pieces = [p for p in re.split(r"[\s'’·\-]+", text) if p]
    # one count for the whole reading: only usable when it isn't already split
    for piece in pieces:
        m = re.fullmatch(r"([a-zǜ-ͯ]+)([1-5])", unicodedata.normalize("NFD", piece))
        if m:
            letters = unicodedata.normalize("NFC", m.group(1))
            if _plain(letters)[0] not in _SYLLABLES and _plain(letters)[0] != "r":
                return ""
            out.append(_syllable(letters, int(m.group(2))))
            continue
        if not re.fullmatch(r"[a-züà-ǜ̀-ͯ]+", unicodedata.normalize("NFC", piece)):
            return ""
        syllables = _split(piece, count if len(pieces) == 1 else None)
        if syllables is None and len(pieces) == 1:
            syllables = _split(piece, None)
        if syllables is None:
            return ""
        out += [_syllable(s, 0) for s in syllables]
    # erhua: ㄦ joins the previous syllable
    joined = []
    for s in out:
        if s == "ㄦ" and joined:
            joined[-1] += "ㄦ"
        else:
            joined.append(s)
    return " ".join(joined)
