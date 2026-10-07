import json
import zipfile

import pytest

from mining import comprehension, dictionaries, frequency, languages, segment, words

HEADERS = {"X-MiningCat": "1"}

EN_TERMS = [[w, "", "", "", 0, [w], i, ""] for i, w in enumerate(["the", "cat", "dog", "eats", "fish", "a"])]


@pytest.fixture(autouse=True)
def en_dict(tmp_path):
    path = tmp_path / "en.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Test English", "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(EN_TERMS))
    segment.clear_cache()
    frequency.clear_cache()
    return dictionaries.import_dictionary(path, "en")


def json_list(tmp_path, items, name="English list.json"):
    path = tmp_path / name
    path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return dictionaries.import_dictionary(path, "en", filename=name)


def known(*expressions, status="known"):
    for expression in expressions:
        words.set_status("en", expression, "", status)


def test_json_list_ranks_words_by_position(tmp_path):
    d = json_list(tmp_path, ["the", ["cat", ""], "fish", "the", "dog"])
    assert d["title"] == "English list" and d["meta_count"] == 4  # the repeated "the" counts once
    assert frequency.ranks(d["id"], d["imported"]) == {"the": 1, "cat": 2, "fish": 3, "dog": 5}
    assert frequency.reference("en")["id"] == d["id"]


def test_text_list_and_errors(tmp_path):
    path = tmp_path / "top.txt"
    path.write_text("# my list\nthe\t1000\ncat,812\n\nfish\n", encoding="utf-8")
    d = dictionaries.import_dictionary(path, "en", filename="top.txt")
    assert frequency.ranks(d["id"], d["imported"]) == {"the": 1, "cat": 2, "fish": 3}

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(dictionaries.DictionaryError, match="no words"):
        dictionaries.import_dictionary(empty, "en", filename="empty.json")
    with pytest.raises(dictionaries.DictionaryError, match="already imported"):
        dictionaries.import_dictionary(path, "en", filename="top.txt")


def test_occurrence_based_yomitan_list(tmp_path):
    path = tmp_path / "counts.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Counts", "revision": "1", "format": 3, "frequencyMode": "occurrence-based"}))
        z.writestr("term_meta_bank_1.json", json.dumps([["cat", "freq", 50], ["the", "freq", {"value": 900, "displayValue": "900"}],
                                                        ["dog", "freq", {"reading": "", "frequency": 7}]]))
    d = dictionaries.import_dictionary(path, "en")
    assert frequency.ranks(d["id"], d["imported"]) == {"the": 1, "cat": 2, "dog": 3}


def test_the_limit_grows_with_the_words_known(tmp_path):
    json_list(tmp_path, ["the", "cat", "fish"])
    assert frequency.frontier("en")["limit"] == frequency.LIMIT_BASE
    known("the", "cat")
    known("dog")  # not in the list: doesn't count
    known("fish", status="learning")
    result = frequency.frontier("en")
    assert result["known"] == 2 and result["limit"] == frequency.LIMIT_BASE + 2 * frequency.LIMIT_PER_KNOWN_WORD


def test_only_frequent_words_are_recommended(tmp_path, monkeypatch):
    monkeypatch.setattr(frequency, "LIMIT_BASE", 10)
    monkeypatch.setattr(frequency, "LIMIT_PER_KNOWN_WORD", 0)
    json_list(tmp_path, ["the", "cat", "eats", "fish"] + [f"w{i}" for i in range(40)] + ["dog"])  # dog: #45
    known("the", "cat", "eats")
    text = "The cat eats fish. The dog eats the cat."
    result = comprehension.evaluate("en", comprehension.profile("en", [text]))
    assert result["i1"] == 2 and result["recommended"] == 1  # dog is too rare for now
    assert result["frequency"]["limit"] == 10

    colours = segment.colour("en", text)
    ranks = {w["headword"]: w["rank"] for w in colours["words"]}
    assert ranks["fish"] == 4 and ranks["dog"] == 45 and colours["frequency"]["limit"] == 10


def test_without_a_list_every_i1_sentence_is_recommended():
    known("the", "cat", "eats")
    result = comprehension.evaluate("en", comprehension.profile("en", ["The cat eats fish. The dog eats the cat."]))
    assert result["recommended"] == result["i1"] == 2 and result["frequency"] is None


def test_choosing_another_list(tmp_path):
    first = json_list(tmp_path, ["cat", "the"], "A.json")
    second = json_list(tmp_path, ["the", "cat"], "B.json")
    assert frequency.reference("en")["id"] == first["id"]
    frequency.choose("en", second["id"])
    assert frequency.Ranker("en").rank("cat") == 2
    dictionaries.update_dictionary(second["id"], enabled=False)  # a disabled list isn't used
    assert frequency.reference("en")["id"] == first["id"]
    with pytest.raises(ValueError):
        frequency.choose("en", 999)


def test_chinese_ranks_ignore_the_script(tmp_path, monkeypatch):
    monkeypatch.setattr(languages, "to_simplified", lambda t, language="zh": t.replace("說", "说"))
    monkeypatch.setattr(languages, "to_traditional", lambda t, language="zh": t.replace("说", "說"))
    path = tmp_path / "zh.json"
    path.write_text(json.dumps(["的", "说"], ensure_ascii=False), encoding="utf-8")
    dictionaries.import_dictionary(path, "zh", filename="zh.json")
    assert frequency.Ranker("zh").rank("說") == 2


def test_lookup_and_settings_api(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    from web import app as web_app
    from web import books
    from web.state import AppState

    monkeypatch.setattr(books, "DIR_LIBRARY", tmp_path / "library")
    client = web_app.create_app(AppState()).test_client()
    d = json_list(tmp_path, ["the", "cat"])
    data = client.post("/api/dict/lookup", json={"language": "en", "text": "cat"}, headers=HEADERS).get_json()
    assert data["entries"][0]["frequency_rank"] == 2 and data["frequency"]["dictionary"]["id"] == d["id"]

    lists = client.get("/api/frequency/lists?language=en").get_json()
    assert lists["chosen"] == d["id"] and lists["frontier"]["words"] == 2
    assert client.post("/api/frequency/list", json={"language": "en", "id": 999}, headers=HEADERS).status_code == 400

    # a JSON list goes through the same import as dictionaries
    client.post("/api/profile", json={"language": "en"}, headers=HEADERS)
    upload = {"file": (open(tmp_path / "English list.json", "rb"), "Other.json")}
    res = client.post("/api/dict/import", data=upload, headers=HEADERS, content_type="multipart/form-data").get_json()
    assert res["title"] == "Other" and res["language"] == "en"
