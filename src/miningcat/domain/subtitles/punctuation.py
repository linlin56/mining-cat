"""Punctuation that Whisper misplaces at the boundaries of the segments, and text prepared for an alignment."""
import re

from miningcat.domain.languages import Language
from miningcat.domain.subtitles.segment import Segment


# Move leading closing punctuation to the end of the previous segment.
def fix_leading_punct(segs: list[Segment], lang: Language = Language.MANDARIN_TW) -> list[Segment]:
    closing_punct = lang.profile.closing_punct
    result: list[Segment] = []
    for seg in segs:
        text = seg.text
        i = 0
        while i < len(text) and text[i] in closing_punct:
            i += 1
        leading = text[:i]
        remainder = text[i:].lstrip()

        if leading and result:
            prev = result[-1]
            result[-1] = Segment(prev.index, prev.start, prev.end, prev.text + leading)
            if remainder:
                result.append(Segment(seg.index, seg.start, seg.end, remainder))
        else:
            result.append(seg)

    return result


# Move trailing opening punctuation (e.g. ¿ ¡) to the start of the next segment.
# Whisper may align ¿/¡ to the tail of the previous segment rather than the head of the question/exclamation, causing it to be dropped or misplaced in the SRT.
def fix_trailing_opening_punct(segs: list[Segment], lang: Language = Language.MANDARIN_TW) -> list[Segment]:
    opening_punct = lang.profile.opening_punct
    if not opening_punct:
        return segs
    result: list[Segment] = list(segs)
    for i in range(len(result) - 1):
        text = result[i].text
        j = len(text)
        while j > 0 and text[j - 1] in opening_punct:
            j -= 1
        trailing = text[j:]
        if not trailing:
            continue
        body = text[:j].rstrip()
        next_seg = result[i + 1]
        result[i] = Segment(result[i].index, result[i].start, result[i].end, body) if body else result[i]
        result[i + 1] = Segment(next_seg.index, next_seg.start, next_seg.end, trailing + next_seg.text)
        if not body:
            result[i] = None  # type: ignore[assignment]
    return [s for s in result if s is not None]


# Restore opening punctuation (¿ ¡ « etc.) that stable-whisper silently drops from
# aligned segments. Searches each segment's text in the reference to detect a
# directly-preceding opening punct char and prepends it when found.
def restore_opening_punct(segs: list[Segment], reference: str, lang: Language) -> list[Segment]:
    opening_punct = lang.profile.opening_punct
    if not opening_punct:
        return segs
    result = []
    ref_pos = 0
    for seg in segs:
        text = seg.text.lstrip()
        if not text or text[0] in opening_punct:
            result.append(Segment(seg.index, seg.start, seg.end, text))
            ref_pos = max(ref_pos, reference.find(text[:12], ref_pos) + 1) if text else ref_pos
            continue
        key = text[:12]
        idx = reference.find(key, ref_pos)
        if idx == -1:
            idx = reference.find(key)
        if idx > 0:
            pre = idx - 1
            while pre >= 0 and reference[pre] in ' \t\n\r':
                pre -= 1
            if pre >= 0 and reference[pre] in opening_punct:
                text = reference[pre] + text
        if idx != -1:
            ref_pos = idx + len(text)
        result.append(Segment(seg.index, seg.start, seg.end, text))
    return result


# The text of a chapter as the alignment needs it: without vocabulary annotations nor empty lines.
def prepare_text(raw: str, lang: Language = Language.MANDARIN_TW) -> str:
    text = re.sub(lang.profile.vocab_annotation_pattern, '', raw)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()
