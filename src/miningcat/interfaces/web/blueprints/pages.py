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


# E-reader: the words sent from KOReader with their sentence, read like the Clipboard (static/inbox.js).
@bp.get("/inbox/")
def inbox_page():
    return render_template("inbox.html")


@bp.get("/settings/")
def settings_page():
    return render_template("settings.html")


# The next words to learn: the most frequent words of the frequency lists not studied yet (static/next_words.js).
@bp.get("/settings/next-words/")
def next_words_page():
    return render_template("next_words.html")
