import pytest

pytest.importorskip("flask")

from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def client():
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_preferences_api(client):
    assert client.get("/api/preferences").get_json() == {"theme": "system", "highlights": "default", "discord": "on"}
    res = client.post("/api/preferences", json={"theme": "dark", "highlights": "deutan"}, headers=HEADERS)
    assert res.get_json() == {"theme": "dark", "highlights": "deutan", "discord": "on"}
    assert client.get("/api/preferences").get_json() == {"theme": "dark", "highlights": "deutan", "discord": "on"}


def test_saving_needs_the_header(client):
    assert client.post("/api/preferences", json={"theme": "dark"}).status_code == 403
    assert client.get("/api/preferences").get_json()["theme"] == "system"


def test_pages_get_the_preferences_before_they_are_drawn(client):
    client.post("/api/preferences", json={"theme": "light", "highlights": "tritan"}, headers=HEADERS)
    page = client.get("/").get_data(as_text=True)
    assert '<html lang="en" data-mc-theme="light" data-mc-highlights="tritan">' in page
