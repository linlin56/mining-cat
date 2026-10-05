import io
import json
import zipfile

import pytest

from mining import anki, db, dictionaries, lookup, words
from mining import languages
from mining.deinflect import transformer_for

pytest.importorskip("flask")

import fake_ankiconnect

HEADERS = {"X-MiningCat": "1"}

# A tiny two-script table so that the tests don't depend on OpenCC.
T2S = dict(zip("說話們國時", "说话们国时"))
S2T = {v: k for k, v in T2S.items()}


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library" / "miningcat.db")
    db.reset_cache()
    monkeypatch.setattr(languages, "to_simplified", lambda t: "".join(T2S.get(c, c) for c in t))
    monkeypatch.setattr(languages, "to_traditional", lambda t: "".join(S2T.get(c, c) for c in t))
    monkeypatch.setattr(words, "to_simplified", languages.to_simplified)
    monkeypatch.setattr(words, "to_traditional", languages.to_traditional)
    yield
    db.reset_cache()


def make_dictionary(path, title, terms, meta=None, tags=None, index_extra=None, images=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": title, "revision": "1", "format": 3, **(index_extra or {})}))
        z.writestr("term_bank_1.json", json.dumps(terms, ensure_ascii=False))
        if meta:
            z.writestr("term_meta_bank_1.json", json.dumps(meta, ensure_ascii=False))
        if tags:
            z.writestr("tag_bank_1.json", json.dumps(tags, ensure_ascii=False))
        for name, data in (images or {}).items():
            z.writestr(name, data)
    return path


ZH_TERMS = [
    ["說", "shuō", "", "", 0, ["to speak; to say"], 0, ""],
    ["說話", "shuōhuà", "", "", 0, [{"type": "structured-content", "content": {"tag": "ul", "content": [{"tag": "li", "content": "to talk"}]}}], 0, ""],
    ["说话", "shuōhuà", "", "", 0, ["to talk (simplified)"], 0, ""],
    ["我們", "wǒmen", "", "", 0, ["we"], 0, ""],
]
JA_TERMS = [
    ["食べる", "たべる", "v1 vt", "v1", 100, ["to eat"], 1, ""],
    ["食べ物", "たべもの", "n", "", 50, ["food"], 2, ""],
    ["行く", "いく", "v5k-s", "v5", 90, ["to go"], 3, ""],
    ["区", "く", "n", "", 10, ["ward"], 5, ""],
    ["た", "た", "aux", "", 0, ["past"], 4, ""],
]


@pytest.fixture
def zh_dict(tmp_path):
    return dictionaries.import_dictionary(make_dictionary(tmp_path / "zh.zip", "Test CEDICT", ZH_TERMS))


@pytest.fixture
def ja_dict(tmp_path):
    return dictionaries.import_dictionary(make_dictionary(
        tmp_path / "ja.zip", "Test JMdict", JA_TERMS,
        meta=[["食べる", "freq", 120], ["行く", "freq", {"value": 30, "displayValue": "30★"}]],
        tags=[["v1", "partOfSpeech", 0, "Ichidan verb", 0]],
        images={"img/a.png": b"\x89PNG"}))


# ---------------------------------------------------------------- languages

def test_language_keys():
    assert languages.language_key("zh-Hant") == "zh"
    assert languages.language_key("zh-HK") == "zh"
    assert languages.language_key("yue-Hant") == "yue"
    assert languages.language_key("ja-JP") == "ja"
    assert languages.language_key("und") == ""


def test_dictionary_language_guess():
    assert languages.guess_dictionary_language([("食べる", "たべる")]) == "ja"
    assert languages.guess_dictionary_language([("說話", "shuōhuà"), ("我們", "wǒmen")]) == "zh"
    assert languages.guess_dictionary_language([("食飯", "sik6 faan6"), ("我哋", "ngo5 dei6")]) == "yue"
    assert languages.guess_dictionary_language([("사랑", "")]) == "ko"


def test_text_variants():
    assert "たべる" in languages.text_variants("タベル", "ja")
    assert "ガ" in languages.text_variants("ｶﾞ", "ja")  # half width becomes full width
    assert "l'homme" in languages.text_variants("L’homme", "fr")


def test_chinese_scripts():
    assert languages.chinese_script("說話") == "traditional"
    assert languages.chinese_script("说话") == "simplified"
    assert languages.chinese_script("天氣") in ("both", "traditional")
    assert languages.chinese_counterpart("說話") == ("simplified", "说话")
    assert languages.chinese_counterpart("我") is None


# ---------------------------------------------------------------- deinflection

def test_japanese_deinflection():
    t = transformer_for("ja")
    results = {d.text: d for d in t.transform("食べなかった")}
    assert "食べる" in results
    names = [x["name"] for x in t.describe(tuple(reversed(results["食べる"].trace)))]
    assert names == ["negative", "-た"]
    assert t.conditions_match(results["食べる"].conditions, t.flags_for_parts_of_speech(["v1"]))
    assert not t.conditions_match(results["食べる"].conditions, t.flags_for_parts_of_speech(["v5k"]))


def test_no_transformer_for_chinese():
    assert transformer_for("zh") is None


# ---------------------------------------------------------------- dictionaries

def test_import_and_list(zh_dict, ja_dict):
    assert zh_dict["language"] == "zh" and zh_dict["term_count"] == 4
    assert ja_dict["language"] == "ja" and ja_dict["meta_count"] == 2
    assert [d["title"] for d in dictionaries.list_dictionaries()] == ["Test JMdict", "Test CEDICT"]
    assert dictionaries.media_path(ja_dict["id"], "img/a.png").read_bytes() == b"\x89PNG"
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.media_path(ja_dict["id"], "../../miningcat.db")


def test_duplicate_and_bad_files(tmp_path, zh_dict):
    with pytest.raises(dictionaries.DictionaryError, match="already imported"):
        dictionaries.import_dictionary(make_dictionary(tmp_path / "again.zip", "Test CEDICT", ZH_TERMS))
    (tmp_path / "bad.zip").write_bytes(b"nope")
    with pytest.raises(dictionaries.DictionaryError):
        dictionaries.inspect(tmp_path / "bad.zip")
    with zipfile.ZipFile(tmp_path / "noindex.zip", "w") as z:
        z.writestr("term_bank_1.json", "[]")
    with pytest.raises(dictionaries.DictionaryError, match="index.json"):
        dictionaries.inspect(tmp_path / "noindex.zip")


def test_source_language_from_index(tmp_path):
    d = dictionaries.import_dictionary(make_dictionary(tmp_path / "x.zip", "X", [["abc", "", "", "", 0, ["x"], 0, ""]],
                                                       index_extra={"sourceLanguage": "fr"}))
    assert d["language"] == "fr"


def test_disable_reorder_delete(zh_dict, tmp_path):
    other = dictionaries.import_dictionary(make_dictionary(tmp_path / "b.zip", "Second", [["說", "shuō", "", "", 0, ["say (2)"], 0, ""]]))
    assert [d["definitions"][0]["dictionary"] for d in lookup.lookup("zh", "說")["entries"]] == ["Test CEDICT"]
    dictionaries.reorder([other["id"], zh_dict["id"]])
    assert lookup.lookup("zh", "說")["entries"][0]["definitions"][0]["dictionary"] == "Second"
    dictionaries.update_dictionary(other["id"], enabled=False)
    assert [d["dictionary"] for d in lookup.lookup("zh", "說")["entries"][0]["definitions"]] == ["Test CEDICT"]
    dictionaries.delete_dictionary(other["id"])
    assert len(dictionaries.list_dictionaries()) == 1


def test_background_import(tmp_path):
    import time
    job = dictionaries.start_import(make_dictionary(tmp_path / "zh.zip", "Bg", ZH_TERMS), "zh", "zh.zip")
    for _ in range(100):
        status = dictionaries.job_status(job)
        if status["done"]:
            break
        time.sleep(0.05)
    assert status["error"] is None and status["dictionary"]["term_count"] == 4


# ---------------------------------------------------------------- lookups

def test_chinese_longest_match(zh_dict):
    result = lookup.lookup("zh", "說話的時候")
    assert result["language"] == "zh"
    assert [(e["expression"], e["length"]) for e in result["entries"]] == [("說話", 2), ("說", 1)]
    assert result["entries"][0]["counterpart"] == {"script": "simplified", "expression": "说话"}


def test_japanese_lookup_with_deinflection_and_frequency(ja_dict):
    entries = lookup.lookup("ja", "食べなかったので")["entries"]
    first = entries[0]
    assert (first["expression"], first["source"]) == ("食べる", "食べなかった")
    assert [i["name"] for i in first["inflections"]] == ["negative", "-た"]
    assert first["frequencies"][0]["display"] == "120"
    assert first["definitions"][0]["tag_info"]["v1"]["notes"] == "Ichidan verb"
    # katakana text finds the hiragana reading
    assert lookup.lookup("ja", "タベモノ")["entries"][0]["expression"] == "食べ物"


def test_part_of_speech_must_match(ja_dict):
    entries = lookup.lookup("ja", "行かなかった")["entries"]
    assert entries[0]["expression"] == "行く"
    # a deinflected form only matches entries with a fitting part of speech: the noun 区 (く) only
    # matches the single character く, never an inflected くない / くなかった
    assert all(e["length"] == 1 for e in lookup.lookup("ja", "くなかった")["entries"] if e["expression"] == "区")


def test_lookup_without_dictionary():
    assert lookup.lookup("ko", "사랑")["dictionaries"] == 0


def test_latin_lookup_uses_word_boundaries(tmp_path):
    dictionaries.import_dictionary(make_dictionary(tmp_path / "fr.zip", "FR", [
        ["chat", "", "", "", 0, ["cat"], 0, ""], ["cha", "", "", "", 0, ["tea?"], 0, ""],
        ["pomme de terre", "", "", "", 0, ["potato"], 0, ""], ["pomme", "", "", "", 0, ["apple"], 0, ""],
    ]), "fr")
    assert [e["expression"] for e in lookup.lookup("fr", "chats dorment")["entries"]] == ["chat"]
    assert lookup.lookup("fr", "Pomme de terre cuite")["entries"][0]["expression"] == "pomme de terre"


# ---------------------------------------------------------------- words

def test_word_statuses_are_per_language():
    words.set_status("zh", "說", "shuō", "known")
    assert words.status_of("zh", "說", "shuō")["status"] == "known"
    assert words.status_of("yue", "說", "syut3")["status"] == "new"
    words.set_status("zh", "說", "Shuō", None)
    assert words.status_of("zh", "說", "shuō")["status"] == "new"


def test_word_without_reading_matches_any_reading():
    words.set_status("zh", "天氣", "", "learning", source="anki")
    assert words.status_of("zh", "天氣", "tiānqì")["status"] == "learning"
    words.set_status("zh", "天氣", "tiān qì", "known")
    assert words.list_words("zh")[0]["reading"] == "tiānqì"


def test_other_script_is_linked():
    words.set_status("zh", "说话", "shuōhuà", "known")
    status = words.status_of("zh", "說話", "shuōhuà")
    assert status["status"] == "new"
    assert status["linked"] == {"script": "simplified", "expression": "说话", "status": "known"}


def test_script_preference(zh_dict):
    assert words.preferred_form("zh", "说话") == "说话"
    words.set_chinese_script_preference("zh", "traditional")
    assert words.preferred_form("zh", "说话") == "說話"
    entry = next(e for e in lookup.lookup("zh", "说话")["entries"] if e["expression"] == "说话")
    assert entry["form"] == "說話"
    with pytest.raises(words.WordError):
        words.set_chinese_script_preference("ja", "traditional")


def test_anki_state_never_overrides_manual_known():
    words.set_status("zh", "我們", "", "known")
    assert words.apply_anki_state("zh", "我們", "", 1, interval=2) == "known"
    assert words.apply_anki_state("zh", "天氣", "", 2, interval=30) == "known"
    assert words.apply_anki_state("zh", "公園", "", 3, interval=2) == "learning"
    assert words.statuses_for("zh", ["我們", "天氣", "公園", "其他"]) == {"我們": "known", "天氣": "known", "公園": "learning"}


# ---------------------------------------------------------------- Anki

@pytest.fixture
def fake_anki():
    server, fake, url = fake_ankiconnect.serve()
    anki.save_config({"url": url})
    yield fake
    server.shutdown()


def setup_chinese_notes():
    fields = anki.guess_field_templates(["Hanzi", "Zhuyin", "Meaning", "Sentence", "Picture", "Sentence Audio"])
    anki.save_config({"notes": {"zh": {"deck": "Mining::Chinese", "model": "Chinese (MiningCat test)", "fields": fields, "tags": "mc"}}})
    return fields


def test_guess_field_templates():
    assert anki.guess_field_templates(["Hanzi", "Zhuyin", "Meaning", "Sentence", "Picture", "Sentence Audio"]) == {
        "Hanzi": "{word}", "Zhuyin": "{reading}", "Meaning": "{definition}", "Sentence": "{sentence}",
        "Picture": "{image}", "Sentence Audio": "{sentence_audio}"}
    assert anki.guess_field_templates(["Front", "Back"]) == {"Front": "{word}", "Back": "{definition}"}
    assert anki.guess_field_templates(["A", "B"]) == {"A": "{word}", "B": "{definition}"}


def test_status_reports_decks(fake_anki):
    status = anki.status()
    assert status["connected"] and "Mining::Chinese" in status["decks"]


def test_card_is_sent_with_media(fake_anki):
    setup_chinese_notes()
    png = "data:image/png;base64," + __import__("base64").b64encode(b"\x89PNGdata").decode()
    card = anki.create_card("zh", {"word": "公園", "reading": "gōngyuán", "definition": "park",
                                   "sentence": "去<b>公園</b>散步"}, {"image": {"data": png, "name": "x.png"}}, "book")
    assert card["status"] == "sent" and card["anki_note_id"]
    note = fake_anki.notes[card["anki_note_id"]]
    assert note["fields"]["Hanzi"] == "公園"
    assert note["fields"]["Sentence"] == "去<b>公園</b>散步"
    assert note["fields"]["Picture"].startswith('<img src="miningcat_')
    assert note["tags"] == ["mc", "book"]
    filename = card["media"]["image"]["filename"]
    assert filename in fake_anki.media
    assert words.status_of("zh", "公園", "gōngyuán")["status"] == "learning"


def test_duplicate_is_refused(fake_anki):
    setup_chinese_notes()
    anki.create_card("zh", {"word": "公園", "definition": "park"}, {})
    second = anki.create_card("zh", {"word": "公園", "definition": "park"}, {})
    assert second["status"] == "failed" and "duplicate" in second["error"]


def test_card_waits_while_anki_is_closed(fake_anki):
    setup_chinese_notes()
    anki.save_config({"url": "http://127.0.0.1:9"})
    card = anki.create_card("zh", {"word": "散步", "definition": "walk"}, {})
    assert card["status"] == "pending" and "reachable" in card["error"]
    assert words.status_of("zh", "散步")["status"] == "learning"
    with pytest.raises(anki.AnkiUnavailable):
        anki.sync()


def test_card_waits_without_note_setup(fake_anki):
    card = anki.create_card("ja", {"word": "猫"}, {})
    assert card["status"] == "pending" and "Settings" in card["error"]


def test_sync_sends_pending_cards_and_reads_statuses(fake_anki):
    setup_chinese_notes()
    url = anki.get_config()["url"]
    anki.save_config({"url": "http://127.0.0.1:9"})
    anki.create_card("zh", {"word": "散步", "definition": "walk"}, {})
    anki.save_config({"url": url, "sync": {"zh": [{"deck": "Mining::Chinese", "field": "Hanzi"}]}})
    fake_anki.add_existing("Mining::Chinese", "Chinese (MiningCat test)", {"Hanzi": "<b>我們</b>"}, interval=40)
    fake_anki.add_existing("Mining::Chinese", "Chinese (MiningCat test)", {"Hanzi": "天氣"}, interval=3)
    fake_anki.add_existing("Mining::Chinese", "Chinese (MiningCat test)", {"Hanzi": "暫停"}, interval=50, suspended=True)
    report = anki.sync()
    assert report["cards"]["sent"] == 1
    assert report["languages"]["zh"]["notes"] == 4  # 3 existing + the card just sent
    assert words.status_of("zh", "我們")["status"] == "known"
    assert words.status_of("zh", "天氣")["status"] == "learning"
    assert words.status_of("zh", "暫停")["status"] == "learning"  # suspended cards don't count
    # a card made in MiningCat matures in Anki
    note_id = anki.list_cards("sent")[0]["anki_note_id"]
    for c in fake_anki.cards.values():
        if c["note"] == note_id:
            c["interval"] = 25
    anki.sync()
    assert words.status_of("zh", "散步")["status"] == "known"


def test_plain_field_values():
    assert anki._plain("<b>漢字</b>&nbsp;") == "漢字"
    assert anki._plain("漢字[かんじ]") == "漢字"
    assert anki._plain("[sound:a.mp3]word") == "word"


def test_config_validation():
    with pytest.raises(anki.AnkiError):
        anki.save_config({"url": "ftp://x"})
    assert anki.save_config({"known_interval": 99999})["known_interval"] == 3650


def test_apkg_export(tmp_path):
    pytest.importorskip("genanki")
    card = anki.create_card("zh", {"word": "公園", "reading": "gōngyuán", "definition": "park"},
                            {"audio": {"data": "data:audio/mpeg;base64,SUQz", "name": "a.mp3"}}, send=False)
    path = anki.export_apkg()
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "collection.anki2" in names
        media = json.loads(z.read("media"))
        assert card["media"]["audio"]["filename"] in media.values()
    assert anki.get_card(card["id"])["status"] == "exported"
    with pytest.raises(anki.AnkiError, match="no cards"):
        anki.export_apkg()


# ---------------------------------------------------------------- HTTP API

@pytest.fixture
def client(tmp_path):
    from web import app as web_app
    from web.state import AppState
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_http_lookup_status_and_cards(client, zh_dict, fake_anki):
    res = client.post("/api/dict/lookup", json={"language": "zh-Hant", "text": "說話"}, headers=HEADERS).get_json()
    assert res["language"] == "zh" and res["entries"][0]["expression"] == "說話"
    assert client.post("/api/dict/lookup", json={"language": "klingon", "text": "x"}, headers=HEADERS).status_code == 400

    assert client.post("/api/words/status", json={"language": "zh", "expression": "說話", "reading": "shuōhuà", "status": "known"},
                       headers=HEADERS).get_json() == {"status": "known"}
    assert client.get("/api/words?language=zh").get_json()["words"][0]["expression"] == "說話"
    assert client.post("/api/words/statuses", json={"language": "zh", "expressions": ["說話", "x"]}, headers=HEADERS).get_json() == {"statuses": {"說話": "known"}}

    setup_chinese_notes()
    card = client.post("/api/cards", json={"language": "zh", "fields": {"word": "我們", "definition": "we"}}, headers=HEADERS).get_json()["card"]
    assert card["status"] == "sent"
    assert client.get("/api/cards?status=sent").get_json()["cards"][0]["expression"] == "我們"
    assert client.get("/api/anki/status").get_json()["connected"] is True
    fields = client.get("/api/anki/fields?model=Basic").get_json()
    assert fields["guess"] == {"Front": "{word}", "Back": "{definition}"}
    assert client.get("/settings/").status_code == 200


def test_http_anki_unavailable(client):
    anki.save_config({"url": "http://127.0.0.1:9"})
    res = client.post("/api/anki/sync", json={}, headers=HEADERS)
    assert res.status_code == 503 and res.get_json()["unavailable"] is True


def test_http_dictionary_import(client, tmp_path):
    import time
    data = make_dictionary(tmp_path / "zh.zip", "Upload", ZH_TERMS).read_bytes()
    res = client.post("/api/dict/import", data={"file": (io.BytesIO(data), "zh.zip"), "language": ""},
                      headers=HEADERS, content_type="multipart/form-data").get_json()
    assert res["language"] == "zh"
    for _ in range(100):
        job = client.get(f"/api/dict/import/{res['job']}").get_json()
        if job["done"]:
            break
        time.sleep(0.05)
    assert job["error"] is None
    assert client.get("/api/dict").get_json()["dictionaries"][0]["title"] == "Upload"
