import pytest

pytest.importorskip("flask")

from miningcat.application import study_language
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def client():
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def receive(client, **values):
    return client.post("/api/inbox", json=values, headers=HEADERS)


def test_a_word_waits_in_the_inbox_until_it_is_removed(client):
    res = receive(client, word="  猫 ", sentence="吾輩は猫である。", language="ja_JP", book="吾輩は猫である", location="12 / 300", sent=1_700_000_000)
    item = res.get_json()["item"]
    assert (item["language"], item["word"], item["sentence"], item["book"], item["location"], item["sent"]) \
        == ("ja", "猫", "吾輩は猫である。", "吾輩は猫である", "12 / 300", 1_700_000_000)
    data = client.get("/api/inbox?language=ja").get_json()
    assert [i["id"] for i in data["items"]] == [item["id"]]
    assert data["counts"] == {"ja": 1}
    assert client.post(f"/api/inbox/{item['id']}/delete", headers=HEADERS).get_json() == {"deleted": True}
    assert client.get("/api/inbox").get_json() == {"items": [], "counts": {}}


def test_the_oldest_word_comes_first_and_languages_are_apart(client):
    receive(client, word="説", sentence="説明", language="zh-TW", sent=20)
    receive(client, word="本", sentence="本を読む", language="ja", sent=30)
    receive(client, word="話", sentence="說話", language="zh", sent=10)
    assert [i["word"] for i in client.get("/api/inbox?language=zh").get_json()["items"]] == ["話", "説"]
    assert [i["word"] for i in client.get("/api/inbox").get_json()["items"]] == ["話", "説", "本"]
    assert client.get("/api/inbox").get_json()["counts"] == {"ja": 1, "zh": 2}


def test_a_word_sent_again_is_added_once(client):
    first = receive(client, word="猫", sentence="猫だ", language="ja", uid="kobo-1").get_json()["item"]
    again = receive(client, word="猫", sentence="猫だ", language="ja", uid="kobo-1").get_json()["item"]
    assert again["id"] == first["id"]
    assert len(client.get("/api/inbox").get_json()["items"]) == 1


def test_without_a_sentence_the_word_is_its_sentence(client):
    assert receive(client, word="猫", language="ja").get_json()["item"]["sentence"] == "猫"


def test_a_book_without_a_known_language_goes_to_the_language_studied(client):
    assert receive(client, word="猫", sentence="猫だ").status_code == 400
    study_language.set_current("ja")
    assert receive(client, word="猫", sentence="猫だ", language="und").get_json()["item"]["language"] == "ja"


def test_what_the_inbox_refuses(client):
    res = receive(client, word=" ", sentence="猫だ", language="ja")
    assert res.status_code == 400 and res.get_json() == {"title": "E-reader", "error": "The word is missing."}
    assert receive(client, word="猫", sentence="あ" * 5_001, language="ja").status_code == 400
    assert client.post("/api/inbox", json={"word": "猫", "language": "ja"}).status_code == 403
    assert client.get("/api/inbox").get_json()["items"] == []


def test_the_page_needs_a_language(client):
    assert client.get("/inbox/").headers["Location"] == "/?next=/inbox/"
    study_language.set_current("ja")
    page = client.get("/inbox/").get_data(as_text=True)
    assert "inbox.js" in page and '"id": "ja"' in page


def test_the_e_reader_can_send_the_text_around_the_word(client):
    item = receive(client, word="猫", before="前の文だ。吾輩は", after="である。次の文。", language="ja").get_json()["item"]
    assert item["sentence"] == "吾輩は猫である。"
