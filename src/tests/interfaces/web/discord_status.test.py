import pytest

pytest.importorskip("flask")

from miningcat.application import study_language
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.discord_status import DiscordStatus, page_activity
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
    assert page_activity("pages.game", {}) == "Playing a game"
    assert page_activity("preferences.api_preferences", {}) is None
    assert page_activity(None, None) is None


def test_the_page_opened_is_shown(client, presence):
    client.get("/reader/some-book")
    activity = presence.shown[-1]
    assert activity.details == "Reading a book"
    assert activity.state == "Studying Japanese"
    assert activity.large_image == "logo"


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
