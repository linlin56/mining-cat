import html
import re

# MiningCat card fields and the marker that inserts each one in a note field.
CARD_FIELDS = {
    "word": "Word",
    "reading": "Reading",
    "zhuyin": "Zhuyin (Mandarin, from the reading)",
    "definition": "Definition",
    "sentence": "Sentence",
    "sentence_translation": "Sentence translation",
    "word_readings": "Word with its reading (Mandarin: 字[zi4])",
    "sentence_readings": "Sentence with the reading of every word (Mandarin: 你[ni3]好[hao3])",
    "notes": "Notes",
    "source": "Source",
    "frequency": "Frequency (rank in your frequency list)",
    "image": "Image",
    "audio": "Word audio",
    "sentence_audio": "Sentence audio",
}

MEDIA_FIELDS = ("image", "audio", "sentence_audio")

# Field names guessed from the user's note type. Each marker goes to the first unused field matching its pattern,
# patterns being tried in this order: a clear "Definitions" field wins over a "Translation" one (in some note
# types, "Translation" is the sentence's), which only gets the definition when there's nothing better.
_GUESSES = [
    (re.compile(r"sentence.*(audio|sound)|(audio|sound).*sentence", re.I), "{sentence_audio}"),
    (re.compile(r"(audio|sound|pronunciation)", re.I), "{audio}"),
    (re.compile(r"(image|picture|screenshot|photo)", re.I), "{image}"),
    (re.compile(r"(translation|english|meaning).*sentence|sentence.*(translation|meaning|english)", re.I), "{sentence_translation}"),
    (re.compile(r"(sentence|example|context|phrase)", re.I), "{sentence}"),
    (re.compile(r"(zhuyin|bopomofo)", re.I), "{zhuyin}"),
    (re.compile(r"(reading|pinyin|furigana|kana|jyutping|pronunciation|romaji)", re.I), "{reading}"),
    (re.compile(r"(definition|meaning|gloss)", re.I), "{definition}"),
    (re.compile(r"(word|expression|vocab|term|hanzi|kanji|front|target|key)", re.I), "{word}"),
    (re.compile(r"(translation|english|back)", re.I), "{definition}"),
    (re.compile(r"(translation|english)", re.I), "{sentence_translation}"),
    (re.compile(r"(source|book|reference)", re.I), "{source}"),
    (re.compile(r"(frequency|freq|rank)", re.I), "{frequency}"),
    (re.compile(r"(note|comment|remark)", re.I), "{notes}"),
]

# Flags of some note types ("Is Vocabulary Card", "Is Audio Card"): never filled with content.
_FLAG_FIELD = re.compile(r"^is\b", re.I)


def guess_field_templates(field_names: list[str]) -> dict[str, str]:
    """Proposes a marker for each field of a note type, from the field names."""
    templates = {name: "" for name in field_names}
    used = set()
    for pattern, template in _GUESSES:
        if template in used:
            continue
        name = next((n for n in field_names if not templates[n] and not _FLAG_FIELD.match(n) and pattern.search(n)), None)
        if name is not None:
            templates[name] = template
            used.add(template)
    if not used and field_names:  # nothing recognised: word on the front, definition on the back
        templates[field_names[0]] = "{word}"
        if len(field_names) > 1:
            templates[field_names[1]] = "{definition}"
    return templates


def media_markup(kind: str, media: dict | None) -> str:
    if not media:
        return ""
    if kind == "image":
        return f'<img src="{html.escape(media["filename"])}">'
    return f"[sound:{media['filename']}]"


_MARKER = re.compile(r"\{([a-z_]+)\}")


def render_template(template: str, fields: dict, media: dict) -> str:
    def replace(match):
        key = match.group(1)
        if key in MEDIA_FIELDS:
            return media_markup("image" if key == "image" else "audio", media.get(key))
        return str(fields.get(key, "") or "")
    return _MARKER.sub(replace, template or "")
