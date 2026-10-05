# anki.py - Sends cards to Anki and reads the state of the user's cards back.
#
# Cards are made in MiningCat's card creator with MiningCat's own fields (word, reading, definition,
# sentence, image, audio...). A per-language "note setup" says which Anki deck and note type to use and
# what to put in each field of that note type, with markers like {word} or {sentence}.
#
# Delivery: AnkiConnect (the Anki add-on, also what a future MiningCat add-on would speak) when Anki
# is open; otherwise the card waits in the database and is sent at the next sync, or can be exported
# to an .apkg file that Anki (desktop, AnkiDroid, AnkiMobile) can import.

import base64
import html
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from mining import db
from mining.word_audio import _ssl_context
from mining import words as words_mod
from mining.languages import LANGUAGES

DEFAULT_URL = "http://127.0.0.1:8765"
ANKICONNECT_VERSION = 6

# MiningCat card fields and the marker that inserts each one in a note field.
CARD_FIELDS = {
    "word": "Word",
    "reading": "Reading",
    "zhuyin": "Zhuyin (Mandarin, from the reading)",
    "definition": "Definition",
    "sentence": "Sentence",
    "sentence_translation": "Sentence translation",
    "notes": "Notes",
    "source": "Source",
    "image": "Image",
    "audio": "Word audio",
    "sentence_audio": "Sentence audio",
}
MEDIA_FIELDS = ("image", "audio", "sentence_audio")

# Field names guessed from the user's note type. Each marker goes to the first unused field matching its pattern,
# patterns being tried in this order: a clear "Definitions" field wins over a "Translation" one (in Migaku's note
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
    (re.compile(r"(note|comment|remark)", re.I), "{notes}"),
]
# Flags of some note types ("Is Vocabulary Card", "Is Audio Card"): never filled with content.
_FLAG_FIELD = re.compile(r"^is\b", re.I)

MEDIA_DIR_NAME = "card_media"


class AnkiError(Exception):
    pass


class AnkiUnavailable(AnkiError):
    """Anki isn't running, or AnkiConnect isn't installed."""


# ---------------------------------------------------------------- settings

DEFAULT_TAG = "mining-cat"
OLD_DEFAULT_TAG = "miningcat"


def get_config() -> dict:
    config = db.get_setting("anki", {}) or {}
    config.setdefault("url", DEFAULT_URL)
    config.setdefault("known_interval", words_mod.DEFAULT_KNOWN_INTERVAL)
    config.setdefault("notes", {})   # language -> {deck, model, fields: {note field: template}, tags}
    config.setdefault("sync", {})    # language -> [{deck, field, reading_field}]
    config.setdefault("tts_voices", {})  # language -> Edge-TTS voice reading the sentences, "" = none
    config.setdefault("translation_language", "en")  # sentences are translated to it, "" = not translated
    for setup in config["notes"].values():
        if setup.get("tags") == OLD_DEFAULT_TAG:  # the default tag was "miningcat" before
            setup["tags"] = DEFAULT_TAG
    return config


def save_config(values: dict) -> dict:
    config = get_config()
    if "url" in values:
        url = str(values["url"] or DEFAULT_URL).strip()
        if not re.match(r"^https?://", url):
            raise AnkiError("The AnkiConnect address must start with http:// or https://")
        config["url"] = url.rstrip("/")
    if "known_interval" in values:
        try:
            config["known_interval"] = max(1, min(3650, int(values["known_interval"])))
        except (TypeError, ValueError):
            raise AnkiError("Invalid interval.")
    for language, setup in (values.get("notes") or {}).items():
        if language not in LANGUAGES:
            continue
        if setup is None:
            config["notes"].pop(language, None)
            continue
        config["notes"][language] = {
            "deck": str(setup.get("deck") or ""),
            "model": str(setup.get("model") or ""),
            "fields": {str(k): str(v) for k, v in (setup.get("fields") or {}).items()},
            "tags": str(setup.get("tags") or DEFAULT_TAG),
        }
    if "translation_language" in values:
        target = str(values["translation_language"] or "")
        if target and target not in LANGUAGES:
            raise AnkiError(f"Unknown language: {target!r}")
        config["translation_language"] = target
    for language, voice in (values.get("tts_voices") or {}).items():
        if language in LANGUAGES:
            config["tts_voices"][language] = str(voice or "")
    for language, sources in (values.get("sync") or {}).items():
        if language not in LANGUAGES:
            continue
        config["sync"][language] = [
            {"deck": str(s.get("deck") or ""), "field": str(s.get("field") or ""), "reading_field": str(s.get("reading_field") or "")}
            for s in (sources or []) if s.get("deck") and s.get("field")
        ]
    db.set_setting("anki", config)
    return config


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


# ---------------------------------------------------------------- AnkiConnect

# The endpoint isn't called "url": storeMediaFile has a "url" param of its own.
def invoke(action: str, endpoint: str | None = None, timeout: float = 10, **params):
    url = endpoint or get_config()["url"]
    payload = json.dumps({"action": action, "version": ANKICONNECT_VERSION, "params": params}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        raise AnkiUnavailable(f"Anki isn't reachable at {url} ({getattr(exc, 'reason', exc)}). Is Anki open with AnkiConnect installed?")
    except ValueError:
        raise AnkiUnavailable(f"{url} didn't answer like AnkiConnect.")
    if not isinstance(data, dict) or "error" not in data:
        raise AnkiUnavailable(f"{url} didn't answer like AnkiConnect.")
    if data["error"]:
        raise AnkiError(str(data["error"]))
    return data["result"]


def status() -> dict:
    """Whether Anki answers, and its decks and note types."""
    try:
        version = invoke("version", timeout=3)
        decks = sorted(invoke("deckNames"))
        models = sorted(invoke("modelNames"))
        return {"connected": True, "version": version, "decks": decks, "models": models}
    except AnkiError as exc:
        return {"connected": False, "error": str(exc), "decks": [], "models": []}


def model_fields(model: str) -> list[str]:
    return invoke("modelFieldNames", modelName=model)


# ---------------------------------------------------------------- card content

def card_media_dir() -> Path:
    return db.DB_PATH.parent / MEDIA_DIR_NAME


def _data_url_bytes(data_url: str) -> tuple[bytes, str]:
    match = re.match(r"^data:([\w/+.-]+)?(;base64)?,(.*)$", data_url, re.S)
    if not match:
        raise AnkiError("Invalid media data.")
    mime = match.group(1) or "application/octet-stream"
    payload = match.group(3)
    raw = base64.b64decode(payload) if match.group(2) else urllib.request.unquote(payload).encode("utf-8")
    return raw, mime


def _extension(mime: str, fallback: str) -> str:
    ext = mimetypes.guess_extension(mime or "") or fallback
    return {".jpe": ".jpg", ".mpga": ".mp3", ".oga": ".ogg"}.get(ext, ext)


def store_media(kind: str, value: dict | None) -> dict | None:
    """Keeps a media file of a card: {data: data URL} is saved locally, {url} is kept as a link."""
    if not value:
        return None
    if value.get("data"):
        raw, mime = _data_url_bytes(value["data"])
        if len(raw) > 30 * 1024 * 1024:
            raise AnkiError("Media files are limited to 30 MB.")
        name = re.sub(r"[^\w.-]", "_", value.get("name") or "")[:60]
        ext = Path(name).suffix or _extension(mime, ".jpg" if kind == "image" else ".mp3")
        filename = f"miningcat_{uuid.uuid4().hex[:16]}{ext}"
        folder = card_media_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_bytes(raw)
        return {"filename": filename, "mime": mime}
    if value.get("url"):
        url = str(value["url"])
        if not re.match(r"^https?://", url):
            raise AnkiError("Media links must start with http:// or https://")
        ext = Path(urllib.request.urlparse(url).path).suffix[:6] or (".jpg" if kind == "image" else ".mp3")
        return {"filename": f"miningcat_{uuid.uuid4().hex[:16]}{ext}", "url": url}
    return None


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


# Fields computed from the card's: the zhuyin of a Mandarin word, from its pinyin reading (CC-CEDICT has no zhuyin).
def derived_fields(language: str, fields: dict) -> dict:
    derived = {}
    if language == "zh" and not fields.get("zhuyin"):
        from mining.zhuyin import pinyin_to_zhuyin
        word = re.sub(r"<[^>]+>", "", fields.get("word", ""))
        derived["zhuyin"] = pinyin_to_zhuyin(re.sub(r"<[^>]+>", "", fields.get("reading", "")), word)
    return derived


def note_fields(setup: dict, fields: dict, media: dict, language: str = "") -> dict[str, str]:
    fields = {**fields, **derived_fields(language, fields)}
    return {name: render_template(template, fields, media) for name, template in setup["fields"].items()}


def _note_setup(language: str) -> dict:
    setup = get_config()["notes"].get(language)
    if not setup or not setup.get("deck") or not setup.get("model") or not setup.get("fields"):
        raise AnkiError(f"Choose the Anki deck and note type for {LANGUAGES.get(language, language)} in Settings › Anki first.")
    return setup


# ---------------------------------------------------------------- the card queue

def _card_row(row) -> dict:
    card = {key: row[key] for key in row.keys()}
    card["fields"] = json.loads(card["fields"])
    card["media"] = json.loads(card["media"])
    return card


def create_card(language: str, fields: dict, media_input: dict, tags: str = "", send: bool = True) -> dict:
    """Saves a card from the card creator, marks its word as learning, and tries to send it to Anki."""
    if language not in LANGUAGES:
        raise AnkiError(f"Unknown language: {language}")
    clean = {key: str(fields.get(key) or "") for key in CARD_FIELDS if key not in MEDIA_FIELDS}
    expression = re.sub(r"<[^>]+>", "", clean["word"]).strip()
    if not expression:
        raise AnkiError("The card has no word.")
    reading = re.sub(r"<[^>]+>", "", clean["reading"]).strip()
    media = {kind: store_media(kind, (media_input or {}).get(kind)) for kind in MEDIA_FIELDS}
    media = {k: v for k, v in media.items() if v}
    now = time.time()
    with db.session() as conn:
        card_id = conn.execute(
            "INSERT INTO cards(language, expression, reading, fields, media, tags, status, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (language, expression, reading, json.dumps(clean, ensure_ascii=False),
             json.dumps(media, ensure_ascii=False), tags.strip(), now, now),
        ).lastrowid
    words_mod.set_status(language, expression, reading, "learning", source="card")
    card = get_card(card_id)
    if send:
        card = send_card(card_id)
    return card


def get_card(card_id: int) -> dict:
    with db.session() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise AnkiError("Unknown card.")
    return _card_row(row)


def list_cards(status: str | None = None, limit: int = 200) -> list[dict]:
    query, params = "SELECT * FROM cards", []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created DESC LIMIT ?"
    params.append(limit)
    with db.session() as conn:
        return [_card_row(r) for r in conn.execute(query, params).fetchall()]


def delete_card(card_id: int) -> None:
    card = get_card(card_id)
    for media in card["media"].values():
        if media and not media.get("url"):
            (card_media_dir() / media["filename"]).unlink(missing_ok=True)
    with db.session() as conn:
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))


def _set_card(card_id: int, **values) -> None:
    values["updated"] = time.time()
    assignments = ", ".join(f"{key} = ?" for key in values)
    with db.session() as conn:
        conn.execute(f"UPDATE cards SET {assignments} WHERE id = ?", [*values.values(), card_id])


def _media_payload(media: dict) -> dict:
    if media.get("url"):
        return {"filename": media["filename"], "url": media["url"]}
    data = (card_media_dir() / media["filename"]).read_bytes()
    return {"filename": media["filename"], "data": base64.b64encode(data).decode("ascii")}


def send_card(card_id: int) -> dict:
    """Sends one card to Anki. If Anki is closed the card stays pending; if Anki refuses it, it fails."""
    card = get_card(card_id)
    if card["status"] == "sent":
        return card
    try:
        setup = _note_setup(card["language"])
    except AnkiError as exc:
        _set_card(card_id, status="pending", error=str(exc))
        return get_card(card_id)
    try:
        for media in card["media"].values():
            invoke("storeMediaFile", **_media_payload(media))
        note = {
            "deckName": setup["deck"],
            "modelName": setup["model"],
            "fields": note_fields(setup, card["fields"], card["media"], card["language"]),
            "tags": [t for t in re.split(r"[\s,]+", f"{setup.get('tags', '')} {card['tags']}") if t],
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        }
        note_id = invoke("addNote", note=note)
    except AnkiUnavailable as exc:
        _set_card(card_id, status="pending", error=str(exc))
        return get_card(card_id)
    except (AnkiError, OSError) as exc:
        _set_card(card_id, status="failed", error=str(exc))
        return get_card(card_id)
    _set_card(card_id, status="sent", error=None, anki_note_id=note_id)
    words_mod.set_status(card["language"], card["expression"], card["reading"], "learning",
                         source="card", anki_note_id=note_id)
    return get_card(card_id)


def send_pending() -> dict:
    sent = failed = waiting = 0
    for card in list_cards("pending", limit=10_000) + list_cards("failed", limit=10_000):
        result = send_card(card["id"])
        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "failed":
            failed += 1
        else:
            waiting += 1
            if "isn't reachable" in (result["error"] or ""):
                break  # Anki is closed: no use trying the others
    return {"sent": sent, "failed": failed, "pending": waiting}


# ---------------------------------------------------------------- reading statuses back

def _plain(value: str) -> str:
    text = re.sub(r"\[sound:[^\]]*\]", "", value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ").strip()
    # furigana written as 漢字[かんじ] in a field
    return re.sub(r"\[[^\]]*\]", "", text).replace(" ", "") if re.search(r"\S\[[^\]]+\]", text) else text


def sync() -> dict:
    """Sends the cards waiting for Anki, then updates word statuses from the user's Anki cards."""
    config = get_config()
    invoke("version", timeout=3)  # raises AnkiUnavailable when Anki is closed
    report = {"cards": send_pending(), "languages": {}}
    known_interval = config["known_interval"]

    for language, sources in config["sync"].items():
        if not sources:
            continue
        updated = {"learning": 0, "known": 0, "kept": 0, "notes": 0}
        for source in sources:
            note_ids = invoke("findNotes", query=f'"deck:{source["deck"]}"')
            for start in range(0, len(note_ids), 500):
                notes = invoke("notesInfo", notes=note_ids[start:start + 500])
                card_ids = [c for n in notes for c in n.get("cards", [])]
                intervals: dict[int, int] = {}
                for c_start in range(0, len(card_ids), 1000):
                    for info in invoke("cardsInfo", cards=card_ids[c_start:c_start + 1000]):
                        if info.get("queue") == -1:  # suspended
                            continue
                        intervals[info["note"]] = max(intervals.get(info["note"], 0), int(info.get("interval") or 0))
                for note in notes:
                    fields = note.get("fields", {})
                    expression = _plain(fields.get(source["field"], {}).get("value", ""))
                    if not expression:
                        continue
                    reading = _plain(fields.get(source["reading_field"], {}).get("value", "")) if source["reading_field"] else ""
                    updated["notes"] += 1
                    status = words_mod.apply_anki_state(
                        language, expression, reading, note["noteId"], intervals.get(note["noteId"], 0), known_interval)
                    updated[status if status in ("learning", "known") else "kept"] += 1
        report["languages"][language] = updated

    # words of cards sent from MiningCat whose deck isn't listed above
    with db.session() as conn:
        rows = conn.execute(
            "SELECT language, expression, reading, anki_note_id FROM words WHERE source = 'card' AND anki_note_id IS NOT NULL"
        ).fetchall()
    if rows:
        note_ids = [r["anki_note_id"] for r in rows]
        intervals: dict[int, int] = {}
        for start in range(0, len(note_ids), 500):
            card_ids = invoke("findCards", query="nid:" + ",".join(str(n) for n in note_ids[start:start + 500]))
            for c_start in range(0, len(card_ids), 1000):
                for info in invoke("cardsInfo", cards=card_ids[c_start:c_start + 1000]):
                    intervals[info["note"]] = max(intervals.get(info["note"], 0), int(info.get("interval") or 0))
        for r in rows:
            if r["anki_note_id"] in intervals:
                words_mod.apply_anki_state(r["language"], r["expression"], r["reading"], r["anki_note_id"],
                                           intervals[r["anki_note_id"]], known_interval)
    db.set_setting("anki_last_sync", time.time())
    return report


# ---------------------------------------------------------------- .apkg export

# Fixed ids so that every export uses the same note type and deck in the user's collection.
APKG_MODEL_ID = 1_740_201_100
APKG_DECK_ID = 1_740_201_200

APKG_FRONT = """<div class="word">{{Word}}</div>
{{#Sentence}}<div class="sentence">{{Sentence}}</div>{{/Sentence}}"""
APKG_BACK = """{{FrontSide}}
<hr id="answer">
<div class="reading">{{Reading}}</div>
{{Word audio}}{{Sentence audio}}
<div class="definition">{{Definition}}</div>
{{#Sentence translation}}<div class="translation">{{Sentence translation}}</div>{{/Sentence translation}}
{{Image}}
{{#Notes}}<div class="notes">{{Notes}}</div>{{/Notes}}
<div class="source">{{Source}}</div>"""
APKG_CSS = """.card { font-family: sans-serif; font-size: 20px; text-align: center; }
.word { font-size: 42px; margin: 12px 0; }
.sentence, .translation { font-size: 22px; margin: 10px 0; }
.sentence b { color: #e0583c; }
.reading { font-size: 24px; color: #666; }
.definition { text-align: left; display: inline-block; }
.notes, .source { font-size: 14px; color: #888; margin-top: 10px; }
img { max-width: 100%; }"""

APKG_FIELD_ORDER = ["word", "reading", "definition", "sentence", "sentence_translation",
                    "image", "audio", "sentence_audio", "notes", "source"]


def export_apkg(card_ids: list[int] | None = None, mark_exported: bool = True) -> Path:
    """Writes the pending (or given) cards to an .apkg file with MiningCat's own note type."""
    try:
        import genanki
    except ImportError:
        raise AnkiError("The .apkg export needs the genanki package (pip install genanki).")
    cards = [get_card(i) for i in card_ids] if card_ids else list_cards("pending", 10_000) + list_cards("failed", 10_000)
    if not cards:
        raise AnkiError("There are no cards to export.")
    model = genanki.Model(
        APKG_MODEL_ID, "MiningCat",
        fields=[{"name": CARD_FIELDS[key]} for key in APKG_FIELD_ORDER],
        templates=[{"name": "Recognition", "qfmt": APKG_FRONT, "afmt": APKG_BACK}],
        css=APKG_CSS,
    )
    decks: dict[str, genanki.Deck] = {}
    media_files = []
    folder = card_media_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for card in cards:
        language = LANGUAGES.get(card["language"], card["language"])
        deck = decks.setdefault(language, genanki.Deck(APKG_DECK_ID + sorted(LANGUAGES).index(card["language"]), f"MiningCat::{language}"))
        for media in card["media"].values():
            path = folder / media["filename"]
            if media.get("url") and not path.exists():
                try:
                    with urllib.request.urlopen(media["url"], timeout=20, context=_ssl_context()) as response:
                        path.write_bytes(response.read())
                except (urllib.error.URLError, OSError):
                    continue
            if path.exists():
                media_files.append(str(path))
        values = []
        for key in APKG_FIELD_ORDER:
            if key in MEDIA_FIELDS:
                values.append(media_markup("image" if key == "image" else "audio", card["media"].get(key)))
            else:
                values.append(card["fields"].get(key, ""))
        guid = genanki.guid_for("miningcat", card["language"], card["expression"], card["reading"], card["id"])
        tags = [re.sub(r"\s", "_", t) for t in re.split(r"[\s,]+", f"{DEFAULT_TAG} {card['tags']}") if t]
        deck.add_note(genanki.Note(model=model, fields=values, guid=guid, tags=tags))
    out_dir = db.DB_PATH.parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"miningcat_{time.strftime('%Y-%m-%d_%H%M%S')}.apkg"
    package = genanki.Package(list(decks.values()))
    package.media_files = sorted(set(media_files))
    package.write_to_file(str(out))
    if mark_exported:
        for card in cards:
            _set_card(card["id"], status="exported", error=None)
    return out
