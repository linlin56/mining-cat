from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)


# Home: the user chooses the language they study, then a screen.
@bp.get("/")
def home():
    return render_template("home.html")


@bp.get("/converter/")
def converter():
    return render_template("converter.html")


# Video game captures, with the dictionary popup and the card creator (see blueprints/game.py).
@bp.get("/game/")
def game_page():
    return render_template("game.html")


# Clipboard: a text typed or pasted by the user, then read with the dictionary popup (static/clipboard.js).
@bp.get("/clipboard/")
def clipboard_page():
    return render_template("clipboard.html")


@bp.get("/settings/")
def settings_page():
    return render_template("settings.html")
