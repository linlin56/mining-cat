import io
import json
import zipfile

import pytest

from miningcat.application.mining import comprehension, dictionaries, preferences, segmentation, words
from miningcat.infrastructure.files.json_files import read_json, write_json

HEADERS = {"X-MiningCat": "1"}

EN_TERMS = [[w, "", "", "", 0, [w], i, ""] for i, w in enumerate(["the", "cat", "dog", "eats", "fish", "a"])]


@pytest.fixture(autouse=True)
def en_dict(tmp_path):
    path = tmp_path / "en.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Test English", "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(EN_TERMS))
    segmentation.clear_cache()
    return dictionaries.import_dictionary(path, "en")


def known(*expressions, status="known"):
    for expression in expressions:
        words.set_status("en", expression, "", status)


def test_sentence_spans():
    text = "Hello there. World!\n「你好。」再見…  Last one"
    assert [text[a:b] for a, b in comprehension.sentence_spans(text)] == ["Hello there.", "World!", "「你好。」", "再見…", "Last one"]
    assert comprehension.sentence_spans("3.5 cats") == [(0, 8)]  # no sentence end inside a number


def test_comprehension_and_recommended_sentences():
    text = "The cat eats fish. The dog eats the cat. Fish, dog! Zorglub the cat."
    known("the", "cat", "eats")
    result = comprehension.evaluate("en", comprehension.profile("en", [text]))
    # 13 dictionary words (Zorglub isn't one): the ×4, cat ×3, eats ×2 known; fish ×2, dog ×2 new
    assert (result["known"], result["new"], result["total"]) == (9, 4, 13)
    assert result["percent"] == round(100 * 9 / 13, 1)
    # "The cat eats fish." and "The dog eats the cat." have one new word; "Fish, dog!" two; the last none
    assert result["recommended"] == 2 and result["sentences"] == 4 and result["unique_new"] == 2

    known("dog", status="learning")  # the only word missing is already being learnt: nothing to mine there
    result = comprehension.evaluate("en", comprehension.profile("en", [text]))
    assert result["recommended"] == 1 and result["learning"] == 2

    known("dog", status="ignored")  # ignored words are left out of the count
    result = comprehension.evaluate("en", comprehension.profile("en", [text]))
    assert result["total"] == 11 and result["recommended"] == 2


def test_lines_are_whole_sentences():
    known("the", "cat")
    data = comprehension.profile("en", ["The cat. The dog", "fish"], whole=True)
    assert len(data["sentences"]) == 2
    assert comprehension.evaluate("en", data)["recommended"] == 2


def test_colour_gives_the_sentences():
    data = segmentation.colour("en", "The cat. A dog.")
    assert data["sentences"] == [[0, 8], [9, 15]]


def test_cached_profile_follows_the_statuses(tmp_path):
    path = tmp_path / "comprehension.json"
    calls = []

    def texts():
        calls.append(1)
        return ["The cat eats fish."]

    assert comprehension.cached(path, "en", 1, texts)["percent"] == 0
    known("the", "cat", "eats")
    assert comprehension.cached(path, "en", 1, texts)["recommended"] == 1
    assert len(calls) == 1  # the text was segmented once
    comprehension.cached(path, "en", 2, texts)
    assert len(calls) == 2  # another version of the text


def test_book_comprehension_endpoint(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    from miningcat.application.library import books
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState

    client = web_app.create_app(AppState()).test_client()
    client.post("/api/profile", json={"language": "en"}, headers=HEADERS)
    text = ("The cat eats the fish and the dog eats the cat. " * 20).encode()
    data = {"files": [(io.BytesIO(text), "cats.txt")]}
    book_id = client.post("/reader/api/books", data=data, headers=HEADERS, content_type="multipart/form-data").get_json()["added"][0]["id"]

    first = client.get(f"/reader/api/books/{book_id}/comprehension").get_json()["comprehension"]
    assert first["percent"] == 0 and first["recommended"] == 0
    known("the", "cat", "eats", "dog")
    second = client.get(f"/reader/api/books/{book_id}/comprehension").get_json()["comprehension"]
    assert second["percent"] > 80 and second["recommended"] == second["sentences"]


def test_video_comprehension_endpoint(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    from miningcat.application.library import books
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState

    folder = tmp_path / "library" / "videos" / "0123456789abcdef"
    (folder / "subs").mkdir(parents=True)
    (folder / "source.mp4").write_bytes(b"x")
    write_json(folder / "meta.json", {"id": "0123456789abcdef", "title": "t", "status": "ready", "language": "en",
                                             "tracks": [{"id": "1", "label": "en", "sha": "a"}]})
    # a line is a sentence, even when its text has two
    (folder / "subs" / "001.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nThe cat. A fish.\n\n"
                                             "2\n00:00:03,000 --> 00:00:04,000\nThe dog eats fish.\n", encoding="utf-8")
    known("the", "cat", "a")
    client = web_app.create_app(AppState()).test_client()
    client.post("/api/profile", json={"language": "en"}, headers=HEADERS)
    result = client.get("/player/api/videos/0123456789abcdef/comprehension").get_json()["comprehension"]
    assert result["sentences"] == 2 and result["recommended"] == 1
    assert result["known"] == 4 and result["new"] == 4
