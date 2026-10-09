import json
from pathlib import Path
from typing import Callable

from miningcat.application.mining import segmentation
from miningcat.application.mining.frequency import Ranker
from miningcat.domain.text.sentences import sentence_spans


def profile(language: str, texts: list[str], whole: bool = False) -> dict:
    """What evaluate() needs of some texts, independent of the word statuses (so it can be cached):
    {"words": [headword], "counts": [occurrences], "sentences": [[word index, ...]]}.
    `whole`: each text is one sentence (a subtitle line), instead of being split into sentences."""
    words: list[str] = []
    index: dict[str, int] = {}
    counts: list[int] = []
    sentences: list[list[int]] = []
    for text in texts:
        tokens = segmentation.segment(language, text)
        spans = [(0, len(text))] if whole else sentence_spans(text)
        k = 0
        for start, end in spans:
            members: list[int] = []
            while k < len(tokens) and tokens[k][0] < end:
                headword = tokens[k][2]
                k += 1
                if headword is None:
                    continue
                if headword not in index:
                    index[headword] = len(words)
                    words.append(headword)
                    counts.append(0)
                i = index[headword]
                counts[i] += 1
                if i not in members:
                    members.append(i)
            if members:
                sentences.append(members)
    return {"words": words, "counts": counts, "sentences": sentences}


def evaluate(language: str, data: dict) -> dict:
    """Comprehension of a profile() with the current word statuses."""
    info = segmentation.statuses(language, data["words"])
    status = [info[h]["status"] for h in data["words"]]
    form = [info[h]["form"] for h in data["words"]]
    totals = {"known": 0, "learning": 0, "new": 0}
    for i, n in enumerate(data["counts"]):
        if status[i] in totals:
            totals[status[i]] += n
    ranker = Ranker(language)
    i1 = recommended = 0
    for members in data["sentences"]:
        missing = {form[i]: i for i in members if status[i] in ("new", "learning")}
        if len(missing) == 1:
            i = next(iter(missing.values()))
            if status[i] == "new":
                i1 += 1
                recommended += ranker.frequent(data["words"][i], form[i])
    total = sum(totals.values())
    return {
        **totals,
        "total": total,
        "percent": round(100 * totals["known"] / total, 1) if total else None,
        "unique_new": len({form[i] for i, s in enumerate(status) if s == "new"}),
        "sentences": len(data["sentences"]),
        "i1": i1,  # sentences with one new word, frequent or not
        "recommended": recommended,
        "frequency": ranker.frontier,
    }


def signature(language: str) -> list:
    """Changes when the dictionaries of the language change: a cached profile is then made again."""
    return [list(part) if isinstance(part, tuple) else part for part in segmentation.lexicon(language).signature]


def cached(path: Path, language: str, version, texts: Callable[[], list[str]], whole: bool = False) -> dict:
    """evaluate() of the profile of `texts()`, made once and kept in `path` until the dictionaries or `version`
    (e.g. which subtitles) change."""
    key = {"language": language, "signature": signature(language), "version": version, "whole": whole}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if not isinstance(saved, dict) or saved.get("key") != key:
        saved = {"key": key, "profile": profile(language, texts(), whole)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    return evaluate(language, saved["profile"])
