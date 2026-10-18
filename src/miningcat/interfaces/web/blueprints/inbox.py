"""The inbox: words sent from an e-reader, waiting for a card. And the e-reader's access to it over the local network
(Settings › E-reader, see lan.py)."""
from flask import Blueprint, jsonify, request

from miningcat.application import ereader_link, inbox, study_language as studied
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import current_state
from miningcat.interfaces.web.requests import json_body, study_language

bp = Blueprint("inbox", __name__)


@bp.post("/api/inbox")
def api_receive():
    """A word sent from the KOReader plugin."""
    return jsonify(item=inbox.receive(json_body()))


@bp.post("/api/inbox/lookup")
def api_lookup():
    """A word looked up on the e-reader, in the user's dictionaries."""
    return jsonify(inbox.lookup(json_body()))


@bp.get("/api/inbox/ping")
def api_ping():
    """The KOReader plugin checks its address and its token."""
    return jsonify(app="MiningCat", language=studied.describe(studied.current()))


@bp.get("/api/inbox")
def api_inbox():
    language = request.args.get("language")
    return jsonify(items=inbox.list_items(study_language(language) if language else None), counts=inbox.counts())


@bp.post("/api/inbox/<int:item_id>/delete")
def api_remove(item_id: int):
    inbox.remove(item_id)
    return jsonify(deleted=True)


def _ereader_access(config: dict) -> dict:
    lan = current_state().lan
    return {**config, "addresses": ereader_link.addresses(config["port"]), **lan.state()}


@bp.get("/api/ereader/config")
def api_ereader_config():
    return jsonify(_ereader_access(ereader_link.get_config()))


@bp.post("/api/ereader/config")
def api_save_ereader_config():
    body = json_body()
    if str(body.get("port", "")).strip() == str(request.environ.get("SERVER_PORT")):
        raise UserError("E-reader", "This port is MiningCat's own: choose another one.")
    config = ereader_link.save_config(body)
    current_state().lan.apply(config)
    return jsonify(_ereader_access(config))


@bp.post("/api/ereader/token")
def api_renew_ereader_token():
    return jsonify(_ereader_access(ereader_link.renew_token()))
