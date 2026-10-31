"""The web GUI: a Flask server on 127.0.0.1, the page opened in the browser."""
import threading
import time
import webbrowser

from flask import Flask
from werkzeug.serving import make_server

from miningcat.application import ereader_link, study_language, user_preferences
from miningcat.infrastructure.system.discord_presence import DiscordPresence
from miningcat.infrastructure.system.updates import UpdateCheck
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
    inbox,
    library_folders,
    pages,
    preferences,
    profile,
    sentence_tools,
    updates,
    videos,
    words,
)
from miningcat.interfaces.web.jobs import AppState
from miningcat.interfaces.web.process import ServerEnd, port_taken, watch_parent
from miningcat.interfaces.web.lan import LanListener

BLUEPRINTS = [
    pages.bp, preferences.bp, profile.bp, converter.bp, converter_files.bp, converter_results.bp, words.bp, dictionaries.bp,
    cards.bp, sentence_tools.bp, books.bp, book_audio.bp, comics.bp, library_folders.bp, videos.bp, game.bp, inbox.bp,
    updates.bp,
]


def create_app(state: AppState | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.extensions["miningcat"] = state or AppState()
    app.extensions["miningcat"].lan = LanListener(app)
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


def main(port: int = 5050, open_browser: bool = True, page: str = "",
         update_check: UpdateCheck | None = None, with_parent: bool = False) -> ServerEnd:
    """Runs the server until Ctrl+C, or until an update stops it. `update_check`: the look for an update made at
    launch, not made again by the home page. `with_parent`: it also stops with the process that started it (see
    process.watch_parent)."""
    presence = DiscordPresence(discord_status.client_id())
    app = create_app(AppState(discord=discord_status.DiscordStatus(presence)))
    state = app.extensions["miningcat"]
    if update_check is not None:
        state.update_check, state.update_checked_at = update_check, time.monotonic()
    # Bound before anything starts: a port taken stops here.
    try:
        server = make_server("127.0.0.1", port, app, threaded=True)
    except OSError as exc:
        print(f"{port_taken(port)} ({exc.strerror or exc})")
        return ServerEnd.PORT_TAKEN
    # The files uploaded and not used before the last stop (not before: another MiningCat, on the port, uses its own)
    uploads.clear_staging()
    end = ServerEnd.STOPPED

    def stop_server(why: ServerEnd) -> None:
        # The server stops, the finally below cleans up. A little later, for the home page's request asking how the
        # update goes to get its answer (it asks every 2 s).
        nonlocal end
        end = why
        threading.Timer(3.0, server.shutdown).start()

    state.stop_server = stop_server
    if with_parent:
        watch_parent(lambda: stop_server(ServerEnd.STOPPED))
    lan = state.lan
    try:
        presence.start()
        if not presence.available:
            print(f"Discord status off: {discord_status.why_off()}")
        url = f"http://127.0.0.1:{port}/{page}"
        print(f"MiningCat is running at {url}  (press Ctrl+C to stop)")
        lan.apply(ereader_link.get_config())
        if lan.error:
            print(f"E-reader access off: {lan.error}")
        if open_browser:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        server.serve_forever()  # until Ctrl+C (Werkzeug catches it) or shutdown; it closes the port
    finally:
        # Stops the video game capture with the server, so it doesn't keep its port and the window capture busy.
        capture = state.game_capture
        if capture is not None:
            capture.stop()
        lan.stop()
        presence.stop()
    return end
