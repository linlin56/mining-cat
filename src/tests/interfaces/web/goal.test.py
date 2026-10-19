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


def test_goal_api(client):
    assert client.get("/api/goals?language=ja").get_json() == {"goals": []}
    assert client.get("/api/goals/plan?language=ja").get_json() == {"goals": []}
    res = client.post("/api/goals", json={"language": "ja", "words": "2000", "by": "2099-06-01"}, headers=HEADERS)
    goal = res.get_json()["goal"]
    assert (goal["words"], goal["by"], goal["status"]) == (2000, "2099-06-01", "active")
    plan = client.get("/api/goals/plan?language=ja").get_json()
    assert plan["current"]["id"] == goal["id"] and plan["plan"]["remaining"] == 2000
    assert client.post("/api/goals", json={"language": "ja", "words": "lots", "by": "2099-06-01"}, headers=HEADERS).status_code == 400
    res = client.post(f"/api/goals/{goal['id']}/delete", json={"language": "ja"}, headers=HEADERS)
    assert res.get_json() == {"goals": []}
