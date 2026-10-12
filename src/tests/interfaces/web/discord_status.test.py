import time

import pytest

pytest.importorskip("flask")

from miningcat.application import study_language
from miningcat.application.game_ocr.settings import GameOcrSettings
from miningcat.interfaces.web import app as web_app
import fake_ankiconnect
from miningcat.interfaces.web.discord_status import DiscordStatus, game_activity, page_activity, studying
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}


class FakePresence:
    def __init__(self):
        self.shown = []

    def show(self, activity):
        self.shown.append(activity)


@pytest.fixture
def presence():
    return FakePresence()


@pytest.fixture
def client(presence):
    study_language.set_current("ja")
    app = web_app.create_app(AppState(discord=DiscordStatus(presence)))
    app.testing = True
    return app.test_client()


def test_page_activities():
    assert page_activity("books.page", {}) == "Choosing a book"
    assert page_activity("books.page", {"book_id": "abc"}) == "Reading a book"
    assert page_activity("player.page", {"video_id": "abc"}) == "Watching a video"
    assert page_activity("pages.game_page", {}) == "Playing a game"
    assert page_activity("preferences.api_preferences", {}) is None
    assert page_activity(None, None) is None


def test_the_page_opened_is_shown(client, presence):
    client.get("/reader/some-book")
    activity = presence.shown[-1]
    assert activity.details == "Reading a book"
    assert activity.state == "Japanese"
    assert activity.large_image == "logo"


# The endpoints of PAGES must be real: a renamed view function would silently drop its status.
def test_every_page_is_an_endpoint(client):
    from miningcat.interfaces.web.discord_status import PAGES
    assert set(PAGES) <= set(client.application.view_functions)


@pytest.mark.parametrize("url, doing", [("/game/", "Playing a game"), ("/clipboard/", "Reading a text"),
                                        ("/settings/", "In the settings")])
def test_pages_are_shown(client, presence, url, doing):
    client.get(url)
    assert presence.shown[-1].details == doing


def test_api_calls_dont_change_it(client, presence):
    client.get("/player/")
    client.get("/api/preferences")
    assert len(presence.shown) == 1
    assert presence.shown[0].details == "Choosing a video"


def test_turned_off_and_on_in_the_settings(client, presence):
    client.get("/settings/")
    client.post("/api/preferences", json={"discord": "off"}, headers=HEADERS)
    assert presence.shown[-1] is None
    client.get("/reader/")
    assert presence.shown[-1] is None
    client.post("/api/preferences", json={"discord": "on"}, headers=HEADERS)
    assert presence.shown[-1].details == "Choosing a book"


def test_game_activity():
    assert game_activity("") == "Playing a game"
    assert game_activity("Sample Quest - Console") == "Playing Sample Quest - Console"
    long = game_activity("x" * 200)
    assert len(long) == 128 and long.endswith("…")


def test_the_game_page_shows_the_source_name(client, presence):
    GameOcrSettings(source_name="Sample Quest").save()
    client.get("/game/")
    assert presence.shown[-1].details == "Playing Sample Quest"
    client.post("/api/game/source-name", json={"source_name": "Other Quest"}, headers=HEADERS)
    assert presence.shown[-1].details == "Playing Other Quest"
    client.post("/api/game/source-name", json={"source_name": ""}, headers=HEADERS)
    assert presence.shown[-1].details == "Playing a game"


def test_renaming_elsewhere_keeps_the_page_shown(client, presence):
    client.get("/reader/")
    client.post("/api/game/source-name", json={"source_name": "Sample Quest"}, headers=HEADERS)
    assert presence.shown[-1].details == "Choosing a book"


def test_studying_line():
    assert studying("ja", 0) == "Japanese"
    assert studying("ja", 12) == "Japanese · 🔥 12-day streak"
    assert studying(None, 3) == "🔥 3-day streak"


def test_the_anki_streak_is_shown(client, presence, monkeypatch):
    from miningcat.application import anki
    from miningcat.application.anki import reviews
    monkeypatch.setattr(reviews, "review_days", reviews.ReviewDays())
    server, fake, url = fake_ankiconnect.serve()
    try:
        anki.save_config({"url": url, "notes": {"ja": {"deck": "Mining::Japanese"}}})
        fake.revlog = [(int(time.time() * 1000), "Mining::Japanese", 1), (int((time.time() - 86400) * 1000), "Mining::Japanese", 1)]
        client.get("/")
        assert client.get("/api/anki/reviews?language=ja").get_json()["streak"] >= 1
        assert "-day streak" in presence.shown[-1].state
        shown = len(presence.shown)
        client.get("/api/anki/reviews?language=ja")
        assert len(presence.shown) == shown  # the same streak: not sent again
        anki.save_config({"notes": {"ja": None}})  # no deck linked any more: no streak
        assert client.get("/api/anki/reviews?language=ja").get_json() == {"linked": False}
        assert presence.shown[-1].state == "Japanese"
    finally:
        server.shutdown()
