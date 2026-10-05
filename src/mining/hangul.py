# Using Yomitan's implementation.
# Yomitan's Korean deinflection rules work on jamo (먹었다 -> ㅁㅓㄱㅇㅓㅆㄷㅏ): a lookup disassembles the
# text, deinflects it, then reassembles the result. Port of Hangul.js 0.2.6 (https://github.com/e-/Hangul.js,
# Copyright 2017 Jaemin Jo, MIT license), which Yomitan uses: the same jamo give the same rule matches.

HANGUL_OFFSET = 0xAC00

CHO = ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
# Complex vowels and final consonants are split too (ㅘ -> ㅗㅏ, ㄳ -> ㄱㅅ).
JUNG = ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅗㅏ", "ㅗㅐ", "ㅗㅣ", "ㅛ", "ㅜ", "ㅜㅓ", "ㅜㅔ", "ㅜㅣ",
        "ㅠ", "ㅡ", "ㅡㅣ", "ㅣ"]
JONG = ["", "ㄱ", "ㄲ", "ㄱㅅ", "ㄴ", "ㄴㅈ", "ㄴㅎ", "ㄷ", "ㄹ", "ㄹㄱ", "ㄹㅁ", "ㄹㅂ", "ㄹㅅ", "ㄹㅌ", "ㄹㅍ", "ㄹㅎ", "ㅁ",
        "ㅂ", "ㅂㅅ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

CONSONANTS = "ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
COMPLETE_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
COMPLETE_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
COMPLETE_JONG = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]

COMPLEX_CONSONANTS = {("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ",
                      ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ",
                      ("ㅂ", "ㅅ"): "ㅄ"}
COMPLEX_VOWELS = {("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ",
                  ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ"}

_CHO_INDEX = {c: i for i, c in enumerate(COMPLETE_CHO)}
_JUNG_INDEX = {c: i for i, c in enumerate(COMPLETE_JUNG)}
_JONG_INDEX = {c: i for i, c in enumerate(COMPLETE_JONG) if c}
_JONG_INDEX[""] = 0


def _is_hangul(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def _is_cho(ch: str) -> bool:
    return ch in _CHO_INDEX


def _is_jung(ch: str) -> bool:
    return ch in _JUNG_INDEX


def _is_jong(ch: str) -> bool:
    return ch in _JONG_INDEX and ch != ""


def disassemble(text: str) -> str:
    """한 -> ㅎㅏㄴ, 와 -> ㅇㅗㅏ, 값 -> ㄱㅏㅂㅅ. Other characters are kept as they are."""
    out = []
    for ch in text:
        if _is_hangul(ch):
            code = ord(ch) - HANGUL_OFFSET
            jong = code % 28
            jung = (code - jong) // 28 % 21
            cho = (code - jong) // 28 // 21
            out.append(CHO[cho] + JUNG[jung] + JONG[jong])
        elif ch in CONSONANTS:
            out.append(CHO[_CHO_INDEX[ch]] if _is_cho(ch) else JONG[_JONG_INDEX[ch]])
        elif _is_jung(ch):
            out.append(JUNG[_JUNG_INDEX[ch]])
        else:
            out.append(ch)
    return "".join(out)


def _syllable(cho: str, jung: str, jong: str = "") -> str:
    return chr((_CHO_INDEX[cho] * 21 + _JUNG_INDEX[jung]) * 28 + _JONG_INDEX[jong] + HANGUL_OFFSET)


def assemble(text: str) -> str:
    """ㅎㅏㄴㄱㅡㄹ -> 한글: the reverse of disassemble(), with Hangul.js's state machine."""
    array = list(disassemble(text))
    result: list[str] = []
    state = {"complete": -1, "jong_joined": False}

    # Builds one character from array[complete + 1 .. index], greedily.
    def make(index: int) -> None:
        state["jong_joined"] = False
        start = state["complete"] + 1
        if start > index:
            return
        cho = jung = jong = None
        hangul = ""
        step = 1
        while True:
            ch = array[state["complete"] + step]
            if step == 1:
                if _is_jung(ch):
                    nxt = array[start + 1] if start + 1 <= index else None
                    if nxt is not None and _is_jung(nxt):
                        result.append(COMPLEX_VOWELS.get((ch, nxt), ch + nxt))
                    else:
                        result.append(ch)
                    state["complete"] = index
                    return
                if not _is_cho(ch):
                    result.append(ch)
                    state["complete"] = index
                    return
                cho = ch
                hangul = ch
            elif step == 2:
                if _is_cho(ch):
                    result.append(COMPLEX_CONSONANTS.get((cho, ch), cho + ch))
                    state["complete"] = index
                    return
                jung = ch
                hangul = _syllable(cho, jung)
            elif step == 3:
                if (jung, ch) in COMPLEX_VOWELS:
                    jung = COMPLEX_VOWELS[(jung, ch)]
                else:
                    jong = ch
                hangul = _syllable(cho, jung, jong or "")
            elif step == 4:
                jong = COMPLEX_CONSONANTS.get((jong, ch), ch) if jong else ch
                hangul = _syllable(cho, jung, jong)
            elif step == 5:
                jong = COMPLEX_CONSONANTS.get((jong, ch), jong)
                hangul = _syllable(cho, jung, jong)
            if state["complete"] + step >= index:
                result.append(hangul)
                state["complete"] = index
                return
            step += 1

    stage = 0
    previous = None
    i = 0
    for i, ch in enumerate(array):
        if not _is_cho(ch) and not _is_jung(ch) and not _is_jong(ch):
            make(i - 1)
            make(i)
            stage = 0
            continue
        if stage == 0:
            if _is_cho(ch):
                stage = 1
            elif _is_jung(ch):
                stage = 4
        elif stage == 1:
            if _is_jung(ch):
                stage = 2
            elif (previous, ch) in COMPLEX_CONSONANTS:
                stage = 5
            else:
                make(i - 1)
        elif stage == 2:
            if _is_jong(ch):
                stage = 3
            elif _is_jung(ch):
                if (previous, ch) not in COMPLEX_VOWELS:
                    make(i - 1)
                    stage = 4
            else:
                make(i - 1)
                stage = 1
        elif stage == 3:
            if _is_jong(ch):
                if not state["jong_joined"] and (previous, ch) in COMPLEX_CONSONANTS:
                    state["jong_joined"] = True
                else:
                    make(i - 1)
                    stage = 1
            elif _is_cho(ch):
                make(i - 1)
                stage = 1
            elif _is_jung(ch):
                make(i - 2)
                stage = 2
        elif stage == 4:
            if _is_jung(ch):
                if (previous, ch) in COMPLEX_VOWELS:
                    make(i)
                    stage = 0
                else:
                    make(i - 1)
            else:
                make(i - 1)
                stage = 1
        elif stage == 5:
            if _is_jung(ch):
                make(i - 2)
                stage = 2
            else:
                make(i - 1)
                stage = 1
        previous = ch
    make(len(array) - 1)
    return "".join(result)
