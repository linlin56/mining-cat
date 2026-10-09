"""Romanized Taigi read by OCR, repaired."""
import re
import unicodedata

from miningcat.domain.text.taigi.romanization import MARK_TONES, NASAL, POJ_DOT, detect, respell

# A romanization read by a Latin OCR model (the Vietnamese one, the richest in marks) comes back with that language's
# look-alike marks. Measured on Tâi-lô and POJ hard subs: the macron (7th tone) is read as a tilde, else a breve or a
# hook above; the circumflex (5th tone) gets a second, Vietnamese, mark (ồ); POJ's o͘ is read as ơ; the vertical line
# (8th tone) as a grave, a hook or an acute. About a third of the macrons and vertical lines aren't seen at all.
_OCR_MACRONS = "\u0303\u0306\u0309"  # ã ă ả (POJ's breve, the 6th tone, is out of use)

_CIRCUMFLEX = "\u0302"

_HORN = "\u031b"

_VERTICAL_LINE = "\u030d"

_OCR_SYLLABLE = re.compile(r"[A-Za-z\u0300-\u036f\u207f]+")


def repair_ocr(text: str) -> str:
    """Romanized Taigi read by OCR, with Tâi-lô / POJ marks for the look-alikes it read: ã -> ā, ồ -> ô, ơ -> o͘, any mark
    on a checked syllable (-p, -t, -k, -h) -> a̍ (only the 8th tone is marked there), and digits read for letters
    (b6 -> bo, 1ang -> lang). The words are then written as usual in their system. A mark the OCR missed stays missing."""
    nfd = unicodedata.normalize("NFD", text)
    if _tone_numbers(nfd):  # no mark to repair, and its digits aren't misread letters
        return text
    not_after_letter = r"(?<![\w\u0300-\u036f])"
    nfd = re.sub(rf"\|(?=[a-z])|{not_after_letter}1(?=[a-z])", "l", nfd)
    nfd = re.sub(rf"(?<=[A-Za-z])[06](?![\w\u0300-\u036f])|(?<=[A-Za-z])[06](?=[a-z])|{not_after_letter}[06](?=[a-z])", "o", nfd)
    # POJ's ⁿ read as a quote or a space, before the hyphen of a word (chiâ"-chò, Siu -beh)
    marks = "".join(MARK_TONES)
    nfd = re.sub(rf'(?<=[a-z{marks}])["\u201d ](?=-[a-z])', NASAL, nfd)
    nfc = unicodedata.normalize("NFC", _OCR_SYLLABLE.sub(lambda m: _repair_syllable(m.group()), nfd))
    system = detect(nfc)
    return respell(nfc, system) if system in ("tailo", "poj") else nfc


def _tone_numbers(nfd: str) -> bool:
    """Whether the text is written with tone numbers (tsiah8): then its digits aren't misread letters."""
    syllables = re.findall(r"[A-Za-z\u0300-\u036f\u207f]+\d?", nfd)
    return bool(syllables) and sum(s[-1].isdigit() for s in syllables) * 2 >= len(syllables)


def _repair_syllable(syllable: str) -> str:
    syllable = syllable.replace("o" + _HORN, "o" + POJ_DOT).replace(_HORN, "")
    # (letter, its marks)
    letters: list[list] = []
    for c in syllable:
        if unicodedata.combining(c) and letters:
            letters[-1][1].append(c)
        else:
            letters.append([c, []])
    tone_marks = [(i, m) for i, (_, marks) in enumerate(letters) for m in marks if m in MARK_TONES or m in _OCR_MACRONS]
    if not tone_marks:
        return syllable
    # the one tone mark kept: a circumflex, else the first other than a breve (a Vietnamese ắ is an acute)
    carrier, mark = next(((i, m) for i, m in tone_marks if m == _CIRCUMFLEX), None) \
        or next(((i, m) for i, m in tone_marks if m != "\u0306"), tone_marks[0])
    plain = "".join(c for c, _ in letters).lower().replace(NASAL, "")
    if plain[-1:] in ("p", "t", "k", "h"):
        mark = _VERTICAL_LINE
    elif mark in _OCR_MACRONS:
        mark = "\u0304"
    out = []
    for i, (c, marks) in enumerate(letters):
        kept = [m for m in marks if m not in MARK_TONES and m not in _OCR_MACRONS]  # POJ's dot, ṳ's diaeresis
        if i == carrier:
            kept.append(mark)
        out.append(c + "".join(kept))
    return "".join(out)
