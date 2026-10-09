from flask import Blueprint, jsonify

from miningcat.application import user_preferences
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("preferences", __name__)


@bp.get("/api/preferences")
def api_preferences():
    return jsonify(user_preferences.get_preferences())


@bp.post("/api/preferences")
def api_save_preferences():
    return jsonify(user_preferences.save_preferences(json_body()))
