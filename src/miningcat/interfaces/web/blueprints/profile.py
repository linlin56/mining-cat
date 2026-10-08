from flask import Blueprint, jsonify

from miningcat.application import study_language
from miningcat.interfaces.web.requests import json_body

bp = Blueprint("profile", __name__)


@bp.get("/api/profile")
def api_profile():
    return jsonify(current=study_language.describe(study_language.current()), languages=study_language.overview())


@bp.post("/api/profile")
def api_set_profile():
    try:
        study_language.set_current(str(json_body().get("language") or ""))
    except ValueError as exc:
        return jsonify(title="Language", error=str(exc)), 400
    return jsonify(current=study_language.describe(study_language.current()))
