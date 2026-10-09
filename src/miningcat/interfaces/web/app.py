"""The web GUI: a Flask server on 127.0.0.1, the page opened in the browser."""
import threading
import webbrowser

from flask import Flask

from miningcat.application import study_language, user_preferences
from miningcat.infrastructure.system.discord_presence import DiscordPresence
from miningcat.interfaces.web import discord_status, errors, security, uploads
from miningcat.interfaces.web.blueprints import (
    book_audio,
    books,
    cards,
    comics,
    converter,
    converter_files,
    converter_results,
    dictionaries,
    game,
    pages,
    preferences,
    profile,
    sentence_tools,
    videos,
    words,
)
from miningcat.interfaces.web.jobs import AppState

BLUEPRINTS = [
    pages.bp, preferences.bp, profile.bp, converter.bp, converter_files.bp, converter_results.bp, words.bp, dictionaries.bp,
    cards.bp, sentence_tools.bp, books.bp, book_audio.bp, comics.bp, videos.bp, game.bp,
]


def create_app(state: AppState | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.extensions["miningcat"] = state or AppState()
    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)
    app.before_request(security.guard)

    @app.before_request
    def _discord_status():
        if app.extensions["miningcat"].discord is not None:
            app.extensions["miningcat"].discord.page_opened()

    errors.register(app)

    # The language studied, for every page's header, and the user's colours (base.html), set before the page is drawn.
    @app.context_processor
    def _study_language():
        return {"study": study_language.describe(study_language.current()),
                "preferences": user_preferences.get_preferences()}

    return app


def main(port: int = 5050, open_browser: bool = True, page: str = "") -> None:
    uploads.clear_staging()
    presence = DiscordPresence(discord_status.client_id())
    presence.start()
    if not presence.available:
        print(f"Discord status off: {discord_status.why_off()}")
    app = create_app(AppState(discord=discord_status.DiscordStatus(presence)))
    url = f"http://127.0.0.1:{port}/{page}"
    print(f"MiningCat is running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
    finally:
        # Stops the video game capture with the server, so it doesn't keep its port and the window capture busy.
        capture = app.extensions["miningcat"].game_capture
        if capture is not None:
            capture.stop()
        presence.stop()
