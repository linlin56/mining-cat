"""Taiwanese Hokkien (Taigi) writing systems: Hanji (漢字), Tâi-lô (the Ministry of Education's romanization) and
Pe̍h-ōe-jī (POJ, the church romanization), and the conversions between them.

Romanized text is read syllable by syllable into a common form (Tâi-lô letters + a tone number), whichever system
it's written in, then written in the wanted one. Hanji are read with taibun (its dictionary is the Ministry of
Education's), and romanized words written in Hanji with the same dictionary reversed: a pronunciation may have
several Hanji, the most common characters are chosen, and a syllable without Hanji stays romanized (Hàn-lô)."""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

SYSTEMS = ("hanji", "tailo", "poj")
LABELS = {"hanji": "Hanji (漢字)", "tailo": "Tâi-lô", "poj": "Pe̍h-ōe-jī (POJ)"}

# combining tone marks -> tone number. POJ writes the 6th tone with a breve, Tâi-lô with a caron.
_MARK_TONES = {"\u0301": 2, "\u0300": 3, "\u0302": 5, "\u030c": 6, "\u0306": 6, "\u0304": 7, "\u030d": 8, "\u030b": 9}
_TAILO_MARKS = {2: "\u0301", 3: "\u0300", 5: "\u0302", 6: "\u030c", 7: "\u0304", 8: "\u030d", 9: "\u030b"}
_POJ_MARKS = {**_TAILO_MARKS, 6: "\u0306"}
_POJ_DOT = "\u0358"  # the dot of POJ's o͘
_NASAL = "\u207f"    # POJ's ⁿ

# A syllable, in Tâi-lô letters without tone: an initial and a final (or a syllabic m / ng).
_SYLLABLE = re.compile(
    r"(?:ph|p|b|m|th|t|n|l|kh|k|g|ng|h|tsh|ts|s|j)?"
    r"(?:(?:iau|uai|ai|au|ia|iu|io|ua|ue|ui|oo|ir|ee|er|a|e|i|o|u)(?:nn)?(?:ng|m|n|p|t|k)?(?:nn)?h?|ng|m)h?"
)
# A romanized word (text in NFD): syllables joined by hyphens, each with an optional tone number.
_LETTERS = r"[A-Za-z\u0300-\u036f\u207f]+\d?"
_ROMAN_WORD = re.compile(rf"(?<![\w\u0300-\u036f]){_LETTERS}(?:-{{1,4}}{_LETTERS})*(?![\w\u0300-\u036f])")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class Syllable:
    letters: str      # Tâi-lô letters, lower case: "tsiah"
    tone: int         # 1 to 9, 0 for a neutral tone given as such ("ah0")
    capital: bool = False
    neutral: bool = False  # written after "--"
    upper: bool = False    # all in capitals (OK, TÂI-OÂN)

    @property
    def key(self) -> str:
        """Pronunciation of the syllable, whatever its spelling: "tsiah8"."""
        return f"{self.letters}{self.tone}"


def _base_tone(letters: str) -> int:
    return 4 if letters[-1:] in ("p", "t", "k", "h") else 1


def parse_syllable(text: str, neutral: bool = False) -> Syllable | None:
    """A syllable in Tâi-lô or POJ, with tone marks or a tone number (tsia̍h, chia̍h, tsiah8). None when it isn't one."""
    text = unicodedata.normalize("NFD", text)
    tone = 0
    digit = re.search(r"\d$", text)
    if digit:
        tone, text = int(digit.group()), text[:-1]
        if tone > 9:
            return None
    marks = [_MARK_TONES[c] for c in text if c in _MARK_TONES]
    if len(marks) > 1:
        return None
    letters = "".join(c for c in text if c not in _MARK_TONES)
    capital = letters[:1].isupper()
    upper = len(letters) > 1 and letters.isupper()
    letters = letters.lower()
    # POJ spellings -> Tâi-lô
    letters = letters.replace("o" + _POJ_DOT, "oo").replace("u\u0324", "ir").replace(_NASAL, "nn")
    letters = letters.replace("chh", "tsh").replace("ch", "ts")
    letters = re.sub(r"o([ae])", r"u\1", letters)
    letters = re.sub(r"e(ng|k)$", r"i\1", letters)
    letters = re.sub(r"hnn$", "nnh", letters)
    if not letters.isascii() or not _SYLLABLE.fullmatch(letters):
        return None
    if not digit:
        tone = marks[0] if marks else _base_tone(letters)
    elif marks and marks[0] != tone:
        return None
    return Syllable(letters, tone, capital, neutral, upper)


def parse_word(word: str) -> list[Syllable] | None:
    """The syllables of a romanized word (tsia̍h-pn̄g, pháinn-sè--lah); None when one of them isn't Taigi."""
    syllables = []
    parts = re.split(r"(-+)", word)
    for i in range(0, len(parts), 2):
        syllable = parse_syllable(parts[i], neutral=i > 0 and len(parts[i - 1]) >= 2)
        if syllable is None:
            return None
        syllables.append(syllable)
    return syllables or None


def _mark_position(letters: str, system: str) -> int:
    """Index of the letter carrying the tone mark."""
    if system == "poj":
        m = re.search(r"o[ae]", letters)
        if m:
            return m.start() if m.end() == len(letters) else m.start() + 1
        order = ("a", "o", "e", "u", "i")
    else:
        if "a" in letters:
            return letters.index("a")
        if "oo" in letters:
            return letters.index("oo")
        for pair, i in (("iu", 1), ("ui", 1)):
            if pair in letters:
                return letters.index(pair) + i
        order = ("e", "o", "i", "u")
    for vowel in order:
        if vowel in letters:
            return letters.index(vowel)
    if "ng" in letters:
        return letters.index("ng")
    return letters.index("m") if "m" in letters else 0


def _poj_letters(letters: str) -> str:
    letters = letters.replace("tsh", "chh").replace("ts", "ch")
    letters = re.sub(r"u([ae])", r"o\1", letters)
    letters = re.sub(r"i(ng|k)$", r"e\1", letters)
    letters = letters.replace("oo", "o" + _POJ_DOT)
    letters = re.sub(r"nnh$", "h" + _NASAL, letters)
    return re.sub(r"nn$", _NASAL, letters)


def write_syllable(syllable: Syllable, system: str = "tailo", numbers: bool = False) -> str:
    """The syllable in Tâi-lô or POJ, with tone marks or (numbers) a tone number."""
    letters = _poj_letters(syllable.letters) if system == "poj" else syllable.letters
    if numbers:
        text = f"{letters}{syllable.tone}"
    else:
        mark = (_POJ_MARKS if system == "poj" else _TAILO_MARKS).get(syllable.tone, "")
        if mark:
            # found without POJ's dot (o͘), which never carries the mark: the mark goes between the o and its dot
            plain = _mark_position(letters.replace(_POJ_DOT, ""), system)
            i = [j for j, c in enumerate(letters) if c != _POJ_DOT][plain]
            letters = letters[:i + 1] + mark + letters[i + 1:]
        text = unicodedata.normalize("NFC", letters)
    if syllable.upper:
        return text.upper()
    return text[:1].upper() + text[1:] if syllable.capital else text


def write_word(syllables: list[Syllable], system: str = "tailo", numbers: bool = False) -> str:
    parts = []
    for i, s in enumerate(syllables):
        if i:
            parts.append("--" if s.neutral else "-")
        parts.append(write_syllable(s, system, numbers))
    return "".join(parts)


def reading_key(reading: str) -> str:
    """Pronunciation of a reading, the same in Tâi-lô and POJ, marks or numbers: "Tâi-oân" and "tai5-uan5" -> "tai5uan5".
    "" when it isn't romanized Taigi."""
    keys = []
    for m in _ROMAN_WORD.finditer(unicodedata.normalize("NFD", reading or "")):
        syllables = parse_word(m.group())
        if syllables is None:
            return ""
        keys += [s.key for s in syllables]
    return "".join(keys)


# ---------------------------------------------------------------- whole texts

def respell(text: str, system: str, numbers: bool = False) -> str:
    """Romanized words of the text written in `system`; the rest (Hanji, other languages) untouched."""
    def replace(m: re.Match) -> str:
        syllables = parse_word(m.group())
        return m.group() if syllables is None else write_word(syllables, system, numbers)
    return unicodedata.normalize("NFC", _ROMAN_WORD.sub(replace, unicodedata.normalize("NFD", text)))


@lru_cache(maxsize=4)
def _converter(system: str, punctuation: str = "format"):
    from taibun import Converter
    return Converter(system=system, punctuation=punctuation)


def _hanji_to_tailo(text: str, punctuation: str = "format") -> str:
    if not _HAN.search(text):
        return text
    try:
        converted = _converter("Tailo", punctuation).get(text)
    except ImportError:
        raise RuntimeError("Reading Hanji needs the taibun package (pip install taibun).")
    # taibun writes an empty neutral-tone syllable for a "--" already in the text (走--矣 -> tsáu----ah)
    return re.sub(r"-{3,}", "--", converted)


def detect(text: str) -> str:
    """The main writing system of a text: 'hanji', 'tailo', 'poj', or '' when there's nothing to tell."""
    han = len(_HAN.findall(text))
    latin = len(_LATIN.findall(text))
    if han and han * 2 >= latin:
        return "hanji"
    if not latin:
        return ""
    nfd = unicodedata.normalize("NFD", text)
    poj = len(re.findall(r"\bchh?|o\u0358|\u207f|\u0306|o[ae]\b", nfd, re.I))
    tailo = len(re.findall(r"\btsh?|oo|nn\b|\u030c|u[ae]\b", nfd, re.I))
    return "poj" if poj > tailo else "tailo"


def convert(text: str, target: str, numbers: bool = False) -> str:
    """The text written in `target` ('hanji', 'tailo' or 'poj'), from any of the three or a mix of them (Hàn-lô).
    numbers: tone numbers instead of tone marks, for a romanization."""
    if target not in SYSTEMS:
        raise ValueError(f"Unknown Taigi writing system: {target!r}")
    if not text:
        return text
    # line by line: taibun joins lines and reformats what isn't Hanji (subtitle timecodes...)
    if "\n" in text:
        return "\n".join(convert(line, target, numbers) for line in text.split("\n"))
    if target == "hanji":
        return to_hanji(text)
    return respell(_hanji_to_tailo(text), target, numbers)


def romanize(text: str, system: str = "tailo", numbers: bool = False) -> str:
    """Romanization of a word or a text (Hanji or another romanization), keeping the original's punctuation."""
    return respell(_hanji_to_tailo(text, "none"), system, numbers)


# ---------------------------------------------------------------- romanized -> Hanji

@lru_cache(maxsize=1)
def _hanji_index() -> tuple[dict[tuple[str, ...], str], int]:
    """{syllable keys: Hanji} from taibun's dictionary, and the longest word in syllables. A pronunciation with
    several Hanji gets the most common word: by its frequency in Chinese (jieba's dictionary: 去 rather than 氣 for
    khì), else by how many words of the dictionary have its characters."""
    from taibun import taibun as data

    counts: dict[str, int] = {}
    for word in data.word_dict:
        for char in word:
            counts[char] = counts.get(char, 0) + 1
    chinese = _chinese_frequencies()
    candidates: dict[tuple[str, ...], list[str]] = {}
    longest = 1
    for word, reading in data.word_dict.items():
        syllables = parse_word(unicodedata.normalize("NFD", reading.strip("-")))
        if not syllables or not _HAN.search(word):
            continue
        key = tuple(s.key for s in syllables)
        candidates.setdefault(key, []).append(word)
        longest = max(longest, len(key))
    score = lambda word: (chinese.get(data.to_simplified(word), 0), sum(counts.get(c, 0) for c in word) / len(word))
    return {key: max(words, key=score) for key, words in candidates.items()}, longest


def _chinese_frequencies() -> dict[str, int]:
    try:
        import jieba
        jieba.setLogLevel(60)
        jieba.initialize()
        return jieba.dt.FREQ
    except Exception:  # jieba missing or its dictionary unreadable: the character counts decide
        return {}


def _word_to_hanji(syllables: list[Syllable], index: dict, longest: int) -> list[tuple[str, bool]]:
    """(text, is_hanji) pieces of a word: the longest dictionary words from the left, a syllable without Hanji as is."""
    pieces, i = [], 0
    while i < len(syllables):
        for n in range(min(longest, len(syllables) - i), 0, -1):
            key = tuple(s.key for s in syllables[i:i + n])
            hanji = index.get(key)
            if hanji is None and n == 1:
                # a neutral-tone syllable (--ah) or a tone sandhi spelling: any tone of the syllable will do
                hanji = next((index[k] for t in range(10) if (k := (f"{syllables[i].letters}{t}",)) in index), None)
            if hanji is not None:
                pieces.append((hanji, True))
                i += n
                break
        else:
            pieces.append((write_word([syllables[i]]), False))
            i += 1
    return pieces


_FULL_WIDTH = str.maketrans({",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"})


def to_hanji(text: str) -> str:
    """Romanized words of the text written in Hanji (best effort: the dictionary's most common characters).
    Hanji and other text stay as they are."""
    try:
        index, longest = _hanji_index()
    except ImportError:
        raise RuntimeError("Writing Hanji needs the taibun package (pip install taibun).")
    nfd = unicodedata.normalize("NFD", text)
    out, last = [], 0
    for m in _ROMAN_WORD.finditer(nfd):
        syllables = parse_word(m.group())
        if syllables is None or any(s.upper for s in syllables):  # OK, TV: not Taigi
            continue
        out.append(nfd[last:m.start()])
        previous_hanji = None
        for piece, is_hanji in _word_to_hanji(syllables, index, longest):
            if previous_hanji is False or (previous_hanji and not is_hanji):
                out.append("-")
            out.append(piece)
            previous_hanji = is_hanji
        last = m.end()
    out.append(nfd[last:])
    result = unicodedata.normalize("NFC", "".join(out))
    # Hanji words aren't separated by spaces, and take full-width punctuation
    han = _HAN.pattern
    result = re.sub(rf"(?<={han}) +(?={han})", "", result)
    result = re.sub(rf"(?<={han})[ ]*([,.!?:;]) *", lambda m: m.group(1).translate(_FULL_WIDTH), result)
    return result


# ---------------------------------------------------------------- readings of Hanji

def reading(hanji: str, system: str = "tailo") -> str:
    """Romanization of a Hanji word ("" when it has no Hanji or taibun isn't installed)."""
    if not _HAN.search(hanji or ""):
        return ""
    try:
        return romanize(hanji, system)
    except RuntimeError:
        return ""


def _tokens(text: str) -> list[str]:
    """The text cut into taibun's words, spaces included. The tokeniser drops spaces and writes some characters
    as variants (臺 -> 台): the pieces are taken from the text itself."""
    from taibun import Tokeniser

    pieces, pos = [], 0
    for token in Tokeniser(False).tokenise(text):
        while pos < len(text) and text[pos].isspace():
            pieces.append(text[pos])
            pos += 1
        pieces.append(text[pos:pos + len(token)])
        pos += len(token)
    if pos < len(text):
        pieces.append(text[pos:])
    return pieces


def annotate(sentence: str, system: str = "tailo") -> list[tuple[str, str]]:
    """(word, reading) pairs of a sentence, reading "" for punctuation and non-Hanji text: 我欲 -> [(我, guá), (欲, beh)]."""
    try:
        tokens = _tokens(sentence)
    except ImportError:
        return [(sentence, "")] if sentence else []
    return [(token, reading(token, system) if _HAN.search(token) else "") for token in tokens]


def tokenize(text: str) -> list[str]:
    """Words of a Taigi text: Hanji words (taibun's tokeniser) and romanized words."""
    text = unicodedata.normalize("NFC", text)
    try:
        tokens = _tokens(text)
    except ImportError:  # one word per character / per run of letters
        tokens = re.findall(rf"{_HAN.pattern}|[^\W\d_](?:[^\W\d_]|[\u0300-\u036f-])*", text)
    return [t for t in tokens if re.search(r"[^\W\d_]", t)]


# ---------------------------------------------------------------- OCR

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
    marks = "".join(_MARK_TONES)
    nfd = re.sub(rf'(?<=[a-z{marks}])["\u201d ](?=-[a-z])', _NASAL, nfd)
    nfc = unicodedata.normalize("NFC", _OCR_SYLLABLE.sub(lambda m: _repair_syllable(m.group()), nfd))
    system = detect(nfc)
    return respell(nfc, system) if system in ("tailo", "poj") else nfc


def _tone_numbers(nfd: str) -> bool:
    """Whether the text is written with tone numbers (tsiah8): then its digits aren't misread letters."""
    syllables = re.findall(r"[A-Za-z\u0300-\u036f\u207f]+\d?", nfd)
    return bool(syllables) and sum(s[-1].isdigit() for s in syllables) * 2 >= len(syllables)


def _repair_syllable(syllable: str) -> str:
    syllable = syllable.replace("o" + _HORN, "o" + _POJ_DOT).replace(_HORN, "")
    # (letter, its marks)
    letters: list[list] = []
    for c in syllable:
        if unicodedata.combining(c) and letters:
            letters[-1][1].append(c)
        else:
            letters.append([c, []])
    tone_marks = [(i, m) for i, (_, marks) in enumerate(letters) for m in marks if m in _MARK_TONES or m in _OCR_MACRONS]
    if not tone_marks:
        return syllable
    # the one tone mark kept: a circumflex, else the first other than a breve (a Vietnamese ắ is an acute)
    carrier, mark = next(((i, m) for i, m in tone_marks if m == _CIRCUMFLEX), None) \
        or next(((i, m) for i, m in tone_marks if m != "\u0306"), tone_marks[0])
    plain = "".join(c for c, _ in letters).lower().replace(_NASAL, "")
    if plain[-1:] in ("p", "t", "k", "h"):
        mark = _VERTICAL_LINE
    elif mark in _OCR_MACRONS:
        mark = "\u0304"
    out = []
    for i, (c, marks) in enumerate(letters):
        kept = [m for m in marks if m not in _MARK_TONES and m not in _OCR_MACRONS]  # POJ's dot, ṳ's diaeresis
        if i == carrier:
            kept.append(mark)
        out.append(c + "".join(kept))
    return "".join(out)


# ---------------------------------------------------------------- speech

def alignment_letters(text: str) -> str:
    """The text as plain lower-case letters for a speech aligner (Hanji read as Tâi-lô, tones dropped):
    我欲食飯 -> "gua beh tsiah png"."""
    tailo = romanize(text, "tailo")
    plain = "".join(c for c in unicodedata.normalize("NFD", tailo) if not unicodedata.combining(c))
    plain = plain.replace(_NASAL, "nn").lower()
    return " ".join(re.findall(r"[a-z]+", plain))


def tts_text(text: str) -> str:
    """The text in POJ with tone marks, how the MMS Taigi voice was trained (Bible recordings)."""
    return romanize(text, "poj")
