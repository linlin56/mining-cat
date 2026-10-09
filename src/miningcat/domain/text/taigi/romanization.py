"""Taigi's romanizations, Tâi-lô (the Ministry of Education's) and Pe̍h-ōe-jī (POJ, the church romanization):
romanized text is read syllable by syllable into a common form (Tâi-lô letters + a tone number), whichever system
it's written in, then written in the wanted one."""
import re
import unicodedata
from dataclasses import dataclass

SYSTEMS = ("hanji", "tailo", "poj")

LABELS = {"hanji": "Hanji (漢字)", "tailo": "Tâi-lô", "poj": "Pe̍h-ōe-jī (POJ)"}

# combining tone marks -> tone number. POJ writes the 6th tone with a breve, Tâi-lô with a caron.
MARK_TONES = {"\u0301": 2, "\u0300": 3, "\u0302": 5, "\u030c": 6, "\u0306": 6, "\u0304": 7, "\u030d": 8, "\u030b": 9}

_TAILO_MARKS = {2: "\u0301", 3: "\u0300", 5: "\u0302", 6: "\u030c", 7: "\u0304", 8: "\u030d", 9: "\u030b"}

_POJ_MARKS = {**_TAILO_MARKS, 6: "\u0306"}

POJ_DOT = "\u0358"  # the dot of POJ's o͘

NASAL = "\u207f"    # POJ's ⁿ

# A syllable, in Tâi-lô letters without tone: an initial and a final (or a syllabic m / ng).
_SYLLABLE = re.compile(
    r"(?:ph|p|b|m|th|t|n|l|kh|k|g|ng|h|tsh|ts|s|j)?"
    r"(?:(?:iau|uai|ai|au|ia|iu|io|ua|ue|ui|oo|ir|ee|er|a|e|i|o|u)(?:nn)?(?:ng|m|n|p|t|k)?(?:nn)?h?|ng|m)h?"
)

# A romanized word (text in NFD): syllables joined by hyphens, each with an optional tone number.
_LETTERS = r"[A-Za-z\u0300-\u036f\u207f]+\d?"

ROMAN_WORD = re.compile(rf"(?<![\w\u0300-\u036f]){_LETTERS}(?:-{{1,4}}{_LETTERS})*(?![\w\u0300-\u036f])")

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]")

LATIN = re.compile(r"[A-Za-z]")


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
    marks = [MARK_TONES[c] for c in text if c in MARK_TONES]
    if len(marks) > 1:
        return None
    letters = "".join(c for c in text if c not in MARK_TONES)
    capital = letters[:1].isupper()
    upper = len(letters) > 1 and letters.isupper()
    letters = letters.lower()
    # POJ spellings -> Tâi-lô
    letters = letters.replace("o" + POJ_DOT, "oo").replace("u\u0324", "ir").replace(NASAL, "nn")
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
    letters = letters.replace("oo", "o" + POJ_DOT)
    letters = re.sub(r"nnh$", "h" + NASAL, letters)
    return re.sub(r"nn$", NASAL, letters)


def write_syllable(syllable: Syllable, system: str = "tailo", numbers: bool = False) -> str:
    """The syllable in Tâi-lô or POJ, with tone marks or (numbers) a tone number."""
    letters = _poj_letters(syllable.letters) if system == "poj" else syllable.letters
    if numbers:
        text = f"{letters}{syllable.tone}"
    else:
        mark = (_POJ_MARKS if system == "poj" else _TAILO_MARKS).get(syllable.tone, "")
        if mark:
            # found without POJ's dot (o͘), which never carries the mark: the mark goes between the o and its dot
            plain = _mark_position(letters.replace(POJ_DOT, ""), system)
            i = [j for j, c in enumerate(letters) if c != POJ_DOT][plain]
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
    for m in ROMAN_WORD.finditer(unicodedata.normalize("NFD", reading or "")):
        syllables = parse_word(m.group())
        if syllables is None:
            return ""
        keys += [s.key for s in syllables]
    return "".join(keys)


def respell(text: str, system: str, numbers: bool = False) -> str:
    """Romanized words of the text written in `system`; the rest (Hanji, other languages) untouched."""
    def replace(m: re.Match) -> str:
        syllables = parse_word(m.group())
        return m.group() if syllables is None else write_word(syllables, system, numbers)
    return unicodedata.normalize("NFC", ROMAN_WORD.sub(replace, unicodedata.normalize("NFD", text)))


def detect(text: str) -> str:
    """The main writing system of a text: 'hanji', 'tailo', 'poj', or '' when there's nothing to tell."""
    han = len(HAN.findall(text))
    latin = len(LATIN.findall(text))
    if han and han * 2 >= latin:
        return "hanji"
    if not latin:
        return ""
    nfd = unicodedata.normalize("NFD", text)
    poj = len(re.findall(r"\bchh?|o\u0358|\u207f|\u0306|o[ae]\b", nfd, re.I))
    tailo = len(re.findall(r"\btsh?|oo|nn\b|\u030c|u[ae]\b", nfd, re.I))
    return "poj" if poj > tailo else "tailo"
