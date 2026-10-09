import re
import unicodedata

# syllables

_INITIALS = {
    "b": "ㄅ", "p": "ㄆ", "m": "ㄇ", "f": "ㄈ", "d": "ㄉ", "t": "ㄊ", "n": "ㄋ", "l": "ㄌ", "g": "ㄍ", "k": "ㄎ", "h": "ㄏ",
    "j": "ㄐ", "q": "ㄑ", "x": "ㄒ", "zh": "ㄓ", "ch": "ㄔ", "sh": "ㄕ", "r": "ㄖ", "z": "ㄗ", "c": "ㄘ", "s": "ㄙ",
}
# Finals after an initial. j, q and x write ü as u: their u, ue, uan and un are the ü ones.
_FINALS = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ", "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ",
    "eng": "ㄥ", "ong": "ㄨㄥ", "i": "ㄧ", "ia": "ㄧㄚ", "ie": "ㄧㄝ", "iao": "ㄧㄠ", "iu": "ㄧㄡ", "ian": "ㄧㄢ", "in": "ㄧㄣ",
    "iang": "ㄧㄤ", "ing": "ㄧㄥ", "iong": "ㄩㄥ", "u": "ㄨ", "ua": "ㄨㄚ", "uo": "ㄨㄛ", "uai": "ㄨㄞ", "ui": "ㄨㄟ",
    "uan": "ㄨㄢ", "un": "ㄨㄣ", "uang": "ㄨㄤ", "ü": "ㄩ", "üe": "ㄩㄝ",
}
_JQX_FINALS = {"u": "ㄩ", "ue": "ㄩㄝ", "uan": "ㄩㄢ", "un": "ㄩㄣ"}
# The finals each initial takes.
_COMBINATIONS = {
    "b": "a o ai ei ao an en ang eng i ie iao ian in ing u",
    "p": "a o ai ei ao ou an en ang eng i ie iao ian in ing u",
    "m": "a o e ai ei ao ou an en ang eng i ie iao iu ian in ing u",
    "f": "a o ei ou an en ang eng u",
    "d": "a e ai ei ao ou an en ang eng ong i ia ie iao iu ian ing u uo ui uan un",
    "t": "a e ai ei ao ou an ang eng ong i ie iao ian ing u uo ui uan un",
    "n": "a e ai ei ao ou an en ang eng ong i ie iao iu ian in iang ing u uo uan un ü üe",
    "l": "a o e ai ei ao ou an ang eng ong i ia ie iao iu ian in iang ing u uo uan un ü üe",
    "g": "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
    "k": "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
    "h": "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
    "j": "i ia ie iao iu ian in iang ing iong u ue uan un",
    "q": "i ia ie iao iu ian in iang ing iong u ue uan un",
    "x": "i ia ie iao iu ian in iang ing iong u ue uan un",
    "zh": "a e ai ei ao ou an en ang eng ong i u ua uo uai ui uan un uang",
    "ch": "a e ai ao ou an en ang eng ong i u ua uo uai ui uan un uang",
    "sh": "a e ai ei ao ou an en ang eng i u ua uo uai ui uan un uang",
    "r": "e ao ou an en ang eng ong i u ua uo ui uan un",
    "z": "a e ai ei ao ou an en ang eng ong i u uo ui uan un",
    "c": "a e ai ao ou an en ang eng ong i u uo ui uan un",
    "s": "a e ai ao ou an en ang eng ong i u uo ui uan un",
}
# Syllables without an initial (y and w spell the medials), and the nasal interjections (呣 m, 嗯 ng, 哼 hng).
_STANDALONE = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ê": "ㄝ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ", "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ",
    "ang": "ㄤ", "eng": "ㄥ", "er": "ㄦ",
    "yi": "ㄧ", "ya": "ㄧㄚ", "yo": "ㄧㄛ", "ye": "ㄧㄝ", "yai": "ㄧㄞ", "yao": "ㄧㄠ", "you": "ㄧㄡ", "yan": "ㄧㄢ",
    "yin": "ㄧㄣ", "yang": "ㄧㄤ", "ying": "ㄧㄥ", "yong": "ㄩㄥ",
    "wu": "ㄨ", "wa": "ㄨㄚ", "wo": "ㄨㄛ", "wai": "ㄨㄞ", "wei": "ㄨㄟ", "wan": "ㄨㄢ", "wen": "ㄨㄣ", "wang": "ㄨㄤ",
    "weng": "ㄨㄥ",
    "yu": "ㄩ", "yue": "ㄩㄝ", "yuan": "ㄩㄢ", "yun": "ㄩㄣ",
    "m": "ㄇ", "n": "ㄋ", "ng": "ㄫ", "hm": "ㄏㄇ", "hng": "ㄏㄫ",
}
_SYLLABIC = {"zh", "ch", "sh", "r", "z", "c", "s"}  # zhi, chi, shi, ri, zi, ci, si: the initial alone


def _build_table() -> dict[str, str]:
    table = dict(_STANDALONE)
    for initial, finals in _COMBINATIONS.items():
        for final in finals.split():
            if final == "i" and initial in _SYLLABIC:
                zhuyin = _INITIALS[initial]
            elif initial in ("j", "q", "x") and final in _JQX_FINALS:
                zhuyin = _INITIALS[initial] + _JQX_FINALS[final]
            else:
                zhuyin = _INITIALS[initial] + _FINALS[final]
            table[initial + final] = zhuyin
    return table


ZHUYIN_OF = _build_table()                              # pinyin syllable (no tone) -> zhuyin
PINYIN_OF = {z: p for p, z in ZHUYIN_OF.items()}        # and back
_LONGEST_PINYIN = max(map(len, ZHUYIN_OF))
_LONGEST_ZHUYIN = max(map(len, PINYIN_OF))

_TONE_OF_MARK = {"̄": 1, "́": 2, "̌": 3, "̀": 4}  # combining macron, acute, caron, grave
_MARK_OF_TONE = {tone: mark for mark, tone in _TONE_OF_MARK.items()}
_ZHUYIN_TONES = {"ˉ": 1, "ˊ": 2, "ˇ": 3, "ˋ": 4}
_ZHUYIN_MARK_OF_TONE = {1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ"}
_VOWELS = set("aeiouüê")
# any bopomofo letter, ㄫ and the dialect ones (ㆠ...) included
_ANY_BOPOMOFO = re.compile(r"[ㄅ-ㄯㆠ-ㆿ]")
_PUNCTUATION = re.compile(r"^[,，。.!?！？;；:：…\-–—]+$")


def is_zhuyin(text: str) -> bool:
    return bool(_ANY_BOPOMOFO.search(text or ""))


def _split(text: str, longest: int, fits) -> list[int] | None:
    """Lengths of the fewest pieces `text` splits into, `fits(i, length)` telling a piece that may be (`longest`
    characters at most); on equal counts, the longest first piece. None when it can't be split."""
    n = len(text)
    best: list[tuple[int, int] | None] = [None] * (n + 1)
    best[n] = (0, 0)
    for i in range(n - 1, -1, -1):
        for length in range(min(n - i, longest), 0, -1):
            if best[i + length] is not None and fits(i, length):
                count = best[i + length][0] + 1
                if best[i] is None or count < best[i][0]:
                    best[i] = (count, length)
    if best[0] is None:
        return None
    lengths, i = [], 0
    while i < n:
        lengths.append(best[i][1])
        i += best[i][1]
    return lengths


# pinyin -> zhuyin

def _letters(word: str) -> list[tuple[str, int]] | None:
    """(letter, tone mark on it or 0) of a pinyin word without digits; None when it has other characters."""
    letters: list[tuple[str, int]] = []
    for char in unicodedata.normalize("NFD", word.lower()):
        if char in _TONE_OF_MARK and letters:
            letters[-1] = (letters[-1][0], _TONE_OF_MARK[char])
        elif char == "̈" and letters and letters[-1][0] == "u":  # u + diaeresis
            letters[-1] = ("ü", letters[-1][1])
        elif char == "̂" and letters and letters[-1][0] == "e":  # ê
            letters[-1] = ("ê", letters[-1][1])
        elif "a" <= char <= "z":
            letters.append(("ü" if char == "v" else char, 0))
        else:
            return None
    return letters


def _pinyin_syllables(word: str, tone: int) -> list[tuple[str, int, bool]] | None:
    """(syllable, tone, erhua) of a run of pinyin letters, `tone` (a number written after it) going to its last
    syllable. Syllables without a tone mark or number are neutral."""
    letters = _letters(word)
    if not letters:
        return None
    text = "".join(c for c, _ in letters)

    def fits(strict: bool):
        def check(i: int, length: int) -> bool:
            piece = text[i:i + length]
            if sum(1 for _, t in letters[i:i + length] if t) > 1:
                return False
            if strict and i > 0 and piece[0] in "aoe":  # needs an apostrophe before it
                return False
            if piece in ZHUYIN_OF:
                return True
            # erhua: an r after the syllable, that no vowel follows (else it's the next syllable's initial)
            return (piece.endswith("r") and piece[:-1] in ZHUYIN_OF and piece != "er"
                    and (i + length == len(text) or text[i + length] not in _VOWELS))
        return check

    # an erhua r makes the longest piece one letter longer
    lengths = _split(text, _LONGEST_PINYIN + 1, fits(True)) or _split(text, _LONGEST_PINYIN + 1, fits(False))
    if lengths is None:
        return None
    syllables, i = [], 0
    for k, length in enumerate(lengths):
        piece = text[i:i + length]
        marked = next((t for _, t in letters[i:i + length] if t), 0)
        erhua = piece not in ZHUYIN_OF
        syllables.append((piece[:-1] if erhua else piece, marked or (tone if k == len(lengths) - 1 and tone else 5), erhua))
        i += length
    return syllables


def _zhuyin_syllable(syllable: str, tone: int, erhua: bool) -> str:
    zhuyin = ZHUYIN_OF[syllable]
    zhuyin = "˙" + zhuyin if tone == 5 else zhuyin + _ZHUYIN_MARK_OF_TONE[tone]
    return zhuyin + ("ㄦ" if erhua else "")


def pinyin_to_zhuyin(pinyin: str) -> str:
    """Zhuyin of a pinyin reading, syllables separated by spaces: "xíngdòng" / "xing2 dong4" -> "ㄒㄧㄥˊ ㄉㄨㄥˋ".
    "" when it isn't pinyin; a reading already in zhuyin is kept."""
    text = unicodedata.normalize("NFC", (pinyin or "").strip())
    if not text:
        return ""
    if is_zhuyin(text):
        return text
    # CC-CEDICT writes ü as u: (lu:4), and erhua with a neutral tone number inside marked pinyin (yīxiàr5)
    text = text.replace("u:", "ü").replace("U:", "Ü")
    text = re.sub(r"(?<=[^\s\d])r5\b", "r", text)
    out: list[str] = []
    for token in re.split(r"[\s'’·・\-]+", text):
        if not token:
            continue
        if _PUNCTUATION.match(token):
            out.append(token)
            continue
        # a tone number ends a syllable: xing2dong4 -> xing 2, dong 4
        parts = re.findall(r"([^\d]+)([1-5]?)", token)
        if "".join(word + number for word, number in parts) != token:
            return ""  # other digits
        for word, number in parts:
            if word.lower() == "r" and out and not _PUNCTUATION.match(out[-1]):
                out[-1] += "ㄦ"  # erhua after a tone number: hua1r
                continue
            syllables = _pinyin_syllables(word, int(number or 0))
            if syllables is None:
                return ""
            out += [_zhuyin_syllable(*s) for s in syllables]
    return " ".join(out)


# zhuyin -> pinyin

def _mark(syllable: str, tone: int) -> str:
    """Pinyin syllable with its tone mark: on a or e, on the o of ou, else on the last vowel (liú, guǐ)."""
    if tone not in _MARK_OF_TONE:
        return syllable
    vowels = [i for i, c in enumerate(syllable) if c in _VOWELS]
    if not vowels:  # m, ng, hm: on the nasal
        at = syllable.index("m") if "m" in syllable else syllable.index("n")
    elif "a" in syllable or "e" in syllable:
        at = syllable.index("a") if "a" in syllable else syllable.index("e")
    elif "ou" in syllable:
        at = syllable.index("o")
    else:
        at = vowels[-1]
    return unicodedata.normalize("NFC", syllable[:at + 1] + _MARK_OF_TONE[tone] + syllable[at + 1:])


def _zhuyin_word(word: str) -> list[tuple[str, int, bool]] | None:
    """(pinyin syllable, tone, erhua) of a zhuyin word (no spaces)."""
    # pieces of letters, each with the tone of its first syllable (a leading ˙) and of its last (a mark after it)
    pieces: list[list] = []  # [letters, first tone, last tone]
    current = None
    for i, char in enumerate(word):
        if char == "˙":
            if i + 1 < len(word) and _ANY_BOPOMOFO.match(word[i + 1]):
                current = ["", 5, 0]  # Taiwan's way: the dot before its syllable
                pieces.append(current)
            elif current is not None and not current[2]:
                current[2] = 5  # a dot after its syllable, at the end of the word
                current = None
            else:
                return None
        elif char in _ZHUYIN_TONES:
            if current is None or not current[0]:
                return None
            current[2] = _ZHUYIN_TONES[char]
            current = None
        elif _ANY_BOPOMOFO.match(char):
            if current is None:
                current = ["", 0, 0]
                pieces.append(current)
            current[0] += char
        else:
            return None

    syllables: list[tuple[str, int, bool]] = []
    for letters, first, last in pieces:
        # a bare ㄦ after a syllable is its erhua (ㄓㄜˋㄦ); toned (ㄦˊ), it's 兒 itself
        if letters == "ㄦ" and not first and not last and syllables and not syllables[-1][2]:
            syllables[-1] = (*syllables[-1][:2], True)
            continue

        def fits(i: int, length: int, letters=letters, last=last) -> bool:
            piece = letters[i:i + length]
            if piece in PINYIN_OF:
                return True
            # erhua: a ㄦ after the syllable, never toned (ㄓㄜˋㄦ). A toned ㄦ is 兒 / 爾 itself: ㄅㄚㄦˇ is bā'ěr.
            toned = last and i + length == len(letters)
            return piece.endswith("ㄦ") and len(piece) > 1 and piece[:-1] in PINYIN_OF and not toned

        lengths = _split(letters, _LONGEST_ZHUYIN + 1, fits)
        if lengths is None:
            return None
        i = 0
        for k, length in enumerate(lengths):
            piece = letters[i:i + length]
            erhua = piece not in PINYIN_OF
            tone = (first if k == 0 and first else 0) or (last if k == len(lengths) - 1 and last else 0) or 1
            syllables.append((PINYIN_OF[piece[:-1] if erhua else piece], tone, erhua))
            i += length
    return syllables


def numbered_pinyin(reading: str) -> str:
    """Pinyin with tone numbers of a zhuyin or pinyin reading, as CC-CEDICT writes it:
    "ㄈㄢˊㄊㄧˇㄗˋ" / "fántǐzì" -> "fan2 ti3 zi4", neutral tone 5, erhua on its syllable ("huar1").
    Punctuation in the reading is dropped; "" when it isn't a reading."""
    zhuyin = pinyin_to_zhuyin(reading)
    syllables = []
    for token in re.split(r"[\s・·]+", zhuyin):
        if not token or _PUNCTUATION.match(token):
            continue
        parsed = _zhuyin_word(token)
        if parsed is None:
            return ""
        syllables += [f"{syllable}{'r' if erhua else ''}{tone}" for syllable, tone, erhua in parsed]
    return " ".join(syllables)


def zhuyin_to_pinyin(zhuyin: str) -> str:
    """Pinyin with tone marks of a zhuyin reading: "ㄒㄧㄥˊ ㄉㄨㄥˋ" -> "xíng dòng", "ㄌㄠˇㄖㄣˊ" -> "lǎorén".
    "" when it isn't zhuyin."""
    text = unicodedata.normalize("NFC", (zhuyin or "").strip())
    if not is_zhuyin(text):
        return ""
    words = []
    for token in re.split(r"[\s・·]+", text):
        if not token:
            continue
        if _PUNCTUATION.match(token):
            words.append(token)
            continue
        syllables = _zhuyin_word(token)
        if syllables is None:
            return ""
        word = ""
        for syllable, tone, erhua in syllables:
            if word and syllable[0] in "aoe":
                word += "'"  # dà'ān
            word += _mark(syllable, tone) + ("r" if erhua else "")
        words.append(word)
    return " ".join(words)
