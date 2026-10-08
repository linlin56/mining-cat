import io

import pytest

pytest.importorskip("flask")

from miningcat.application import anki
from miningcat.application import study_language as profile
from miningcat.application.library import books
from miningcat.application.mining import preferences, words
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}

JA_TEXT = "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。" * 5
ZH_TEXT = "我們今天說話。這個國家的時候，他們都來了。" * 5


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def choose(client, language):
    return client.post("/api/profile", json={"language": language}, headers=HEADERS)


def test_pages_ask_for_a_language_first(client):
    assert client.get("/").status_code == 200
    for page in ("/converter/", "/reader/", "/player/", "/settings/"):
        res = client.get(page)
        assert res.status_code == 302 and res.headers["Location"] == f"/?next={page}"
    assert client.get("/api/profile").get_json()["current"] is None

    assert choose(client, "zh").get_json()["current"]["name"] == "Mandarin"
    page = client.get("/converter/")
    assert page.status_code == 200 and "Mandarin".encode() in page.data


def test_unknown_language_is_refused(client):
    assert choose(client, "klingon").status_code == 400
    assert profile.current() is None


def test_home_lists_every_language_with_its_words(client):
    words.set_status("ja", "猫", "ねこ", "known")
    languages = {l["id"]: l for l in client.get("/api/profile").get_json()["languages"]}
    assert languages["ja"]["words"] == 1 and languages["ja"]["native"] == "日本語"
    assert languages["nan"]["converter"] is False
    assert languages["yue"]["converter"] is True


def test_converter_only_offers_the_variants_of_the_language(client):
    choose(client, "zh")
    options = client.get("/api/options").get_json()
    assert [l["id"] for l in options["languages"]] == ["mandarin_tw", "mandarin_cn"]
    assert options["default_language"] == "mandarin_tw"

    preferences.set_chinese_script_preference("zh", "simplified")
    assert client.get("/api/options").get_json()["default_language"] == "mandarin_cn"
    assert profile.default_tag("zh") == "zh-Hans"

    choose(client, "fr")
    assert [l["id"] for l in client.get("/api/options").get_json()["languages"]] == ["french"]
    choose(client, "nan")
    options = client.get("/api/options").get_json()
    assert options["languages"] == [] and options["default_language"] is None


def test_reader_library_holds_the_books_of_the_language(client):
    choose(client, "yue")
    data = {"files": [(io.BytesIO(ZH_TEXT.encode()), "hk.txt"), (io.BytesIO(JA_TEXT.encode()), "neko.txt")]}
    res = client.post("/reader/api/books", data=data, headers=HEADERS, content_type="multipart/form-data").get_json()
    assert len(res["added"]) == 2
    assert res["elsewhere"] == ["neko (Japanese)"]

    # detection calls Chinese text Mandarin: imported while studying Cantonese, the book is Cantonese
    shown = client.get("/reader/api/books").get_json()["books"]
    assert [b["title"] for b in shown] == ["hk"]
    assert books.get_prefs(shown[0]["id"])["language"] == "yue-Hant"

    choose(client, "ja")
    assert [b["title"] for b in client.get("/reader/api/books").get_json()["books"]] == ["neko"]


def test_cards_are_listed_per_language(client):
    anki.create_card("zh", {"word": "我們"}, {}, "", send=False)
    anki.create_card("ja", {"word": "猫"}, {}, "", send=False)
    cards = client.get("/api/cards?language=ja").get_json()["cards"]
    assert [c["expression"] for c in cards] == ["猫"]
    assert len(client.get("/api/cards").get_json()["cards"]) == 2
