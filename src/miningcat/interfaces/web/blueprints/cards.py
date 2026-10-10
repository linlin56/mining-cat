"""Anki: its setup, the card queue, status sync and .apkg export."""
from flask import Blueprint, jsonify, request, send_file

from miningcat.application import anki
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("cards", __name__)


@bp.get("/api/anki/status")
def api_anki_status():
    return jsonify(anki.status())


@bp.get("/api/anki/config")
def api_anki_config():
    return jsonify(config=anki.get_config(), card_fields=anki.CARD_FIELDS)


@bp.post("/api/anki/config")
def api_save_anki_config():
    return jsonify(config=anki.save_config(json_body()))


@bp.get("/api/anki/fields")
def api_anki_fields():
    model = request.args.get("model", "")
    language = request.args.get("language")
    fields = anki.model_fields(model)
    return jsonify(fields=fields, guess=anki.guess_field_templates(fields, study_language(language) if language else ""))


@bp.get("/api/anki/deck-fields")
def api_anki_deck_fields():
    """The fields of the notes of a deck, for the decks whose words' statuses are read."""
    return jsonify(fields=anki.deck_fields(request.args.get("deck", "")))


@bp.post("/api/anki/deck")
def api_anki_deck():
    """Creates MiningCat's deck of a language in Anki."""
    return jsonify(anki.create_deck(study_language(json_body().get("language"))))


@bp.post("/api/anki/note-type")
def api_anki_note_type():
    """Creates (or updates) MiningCat's note type in Anki."""
    return jsonify(anki.install_note_type(study_language(json_body().get("language"))))


@bp.post("/api/anki/sync")
def api_anki_sync():
    return jsonify(anki.sync())


@bp.post("/api/cards")
def api_create_card():
    body = json_body()
    card = anki.create_card(study_language(body.get("language")), body.get("fields") or {}, body.get("media") or {},
                            str(body.get("tags") or ""), send=body.get("send", True) is not False,
                            key_reading=str(body.get("key_reading") or ""))
    return jsonify(card=card)


@bp.get("/api/cards")
def api_cards():
    language = request.args.get("language")
    return jsonify(cards=anki.list_cards(request.args.get("status") or None, language=study_language(language) if language else None))


@bp.post("/api/cards/<int:card_id>/send")
def api_send_card(card_id: int):
    return jsonify(card=anki.send_card(card_id))


@bp.post("/api/cards/send-pending")
def api_send_pending():
    language = json_body().get("language")
    return jsonify(anki.send_pending(study_language(language) if language else None))


@bp.post("/api/cards/<int:card_id>/delete")
def api_delete_card(card_id: int):
    anki.delete_card(card_id)
    return jsonify(deleted=True)


@bp.post("/api/cards/export")
def api_export_cards():
    body = json_body()
    ids = body.get("ids")
    if not ids and body.get("language"):
        language = study_language(body["language"])
        ids = [c["id"] for status in ("pending", "failed") for c in anki.list_cards(status, 10_000, language=language)]
        if not ids:
            raise anki.AnkiError("There are no cards to export.")
    path = anki.export_apkg([int(i) for i in ids] if ids else None)
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/octet-stream")


@bp.get("/api/cards/media/<path:name>")
def api_card_media(name: str):
    base = anki.card_media_dir().resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise UserError("Error", "No such file.", 404)
    return send_file(path)
