"""Guessing the language of a text from its characters and frequent words."""
import re

_KANA = re.compile(r"[぀-ヿ]")

_HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")

_HAN = re.compile(r"[一-鿿㐀-䶿]")

_LATIN = re.compile(r"[A-Za-zÀ-ɏ]")

# Very frequent characters that only exist in one of the two scripts.
_TRAD_ONLY = set("這們個說國對來時會為們與從學後還麼開關見話讓認經長過現發問進點樣頭邊應實當")

_SIMP_ONLY = set("这们个说国对来时会为们与从学后还么开关见话让认经长过现发问进点样头边应实当")

_LATIN_HINTS = {
    "fr": {" le ", " la ", " les ", " des ", " est ", " une ", " et ", " que ", " pas ", " dans "},
    "es": {" el ", " los ", " las ", " una ", " que ", " y ", " por ", " para ", " está "},
    "it": {" il ", " gli ", " della ", " una ", " che ", " non ", " sono ", " per "},
    "de": {" der ", " die ", " und ", " nicht ", " ist ", " ein ", " eine ", " ich "},
    "pt": {" não ", " uma ", " os ", " que ", " para ", " com ", " está "},
    "pl": {" się ", " nie ", " jest ", " że ", " na ", " i ", " to "},
    "vi": {" của ", " và ", " là ", " không ", " có ", " người "},
    "en": {" the ", " and ", " of ", " to ", " is ", " that ", " was "},
}


# Guesses a BCP-47 language tag from a text sample (used for TXT files, and to fix EPUBs whose
# metadata language is obviously wrong, e.g. a Japanese book tagged "fr" by its authoring tool).
def detect_language(text: str) -> str | None:
    sample = text[:40_000]
    kana, hangul, han = len(_KANA.findall(sample)), len(_HANGUL.findall(sample)), len(_HAN.findall(sample))
    latin = len(_LATIN.findall(sample))
    if kana > 20 and kana >= han * 0.1:
        return "ja"
    if hangul > 20 and hangul >= han:
        return "ko"
    if han > 20 and han > latin:
        trad = sum(1 for ch in sample if ch in _TRAD_ONLY)
        simp = sum(1 for ch in sample if ch in _SIMP_ONLY)
        return "zh-Hans" if simp > trad else "zh-Hant"
    if latin > 50:
        lowered = f" {sample.lower()} "
        scores = {lang: sum(lowered.count(w) for w in words) for lang, words in _LATIN_HINTS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else None
    return None


def script_family(lang: str | None) -> str:
    lang = (lang or "").lower()
    if lang.startswith(("ja",)):
        return "ja"
    if lang.startswith(("zh", "yue", "cmn")):
        return "zh"
    if lang.startswith("ko"):
        return "ko"
    return "latin" if lang else ""


def pick_language(declared: str | None, sample: str) -> str:
    """The language of a book: the declared one, unless its sample is obviously in another script."""
    detected = detect_language(sample)
    if not declared:
        return detected or "und"
    if detected and script_family(detected) != script_family(declared):
        return detected
    if declared.lower() in ("zh", "zh-cn", "zh-sg"):
        return "zh-Hans"
    if declared.lower() in ("zh-tw", "zh-hk", "zh-mo"):
        return "zh-Hant"
    return declared
