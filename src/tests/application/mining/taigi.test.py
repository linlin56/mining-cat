import importlib.util
import json
import zipfile

import pytest

from miningcat.application.anki.note_fields import derived_fields
from miningcat.application.mining import dictionaries, lookup, preferences, segmentation, words
from miningcat.domain.dictionary.language_guess import guess_dictionary_language
from miningcat.domain.text.readings import normalize_reading, reading_key, reading_match
from miningcat.domain.text.variants import text_variants
from miningcat.domain.words.status import WordError

HEADERS = {"X-MiningCat": "1"}
needs_taibun = pytest.mark.skipif(importlib.util.find_spec("taibun") is None, reason="taibun isn't installed")


def test_text_variants_and_readings():
    assert text_variants("Chia̍h-pn̄g", "nan") == ["Chia̍h-pn̄g", "chia̍h-pn̄g", "tsia̍h-pn̄g", "tsiah8-png7"]
    assert text_variants("食飯", "nan") == ["食飯"]
    assert normalize_reading("Chia̍h-pn̄g", "nan") == normalize_reading("tsia̍h-pn̄g", "nan") == "tsia̍hpn̄g"
    assert reading_key("chia̍h-pn̄g", "nan") == reading_key("tsiah8 png7", "nan")
    assert reading_match("tsiah8-png7", "tsia̍h-pn̄g", "nan") == 2
    assert reading_match("tsiah4-png7", "tsia̍h-pn̄g", "nan") == 1
    assert reading_match("guá", "tsia̍h-pn̄g", "nan") == 0


def test_taigi_dictionaries_are_recognized():
    samples = [("食飯", "tsia̍h-pn̄g"), ("台灣", "Tâi-uân"), ("歹勢", "pháinn-sè"), ("媠", "suí"), ("有", "ū")]
    assert guess_dictionary_language(samples) == "nan"
    assert guess_dictionary_language([("吃饭", "chī fàn"), ("台湾", "tái wān"), ("好", "hǎo")]) == "zh"


def test_reading_system_setting():
    assert preferences.reading_system("nan") == "tailo"
    assert words.display_reading("nan", "食飯", "chia̍h-pn̄g") == "tsia̍h-pn̄g"
    preferences.set_reading_system("nan", "poj")
    assert preferences.reading_system("nan") == "poj"
    assert words.display_reading("nan", "食飯", "tsia̍h-pn̄g") == "chia̍h-pn̄g"
    with pytest.raises(WordError):
        preferences.set_reading_system("nan", "pinyin")
    with pytest.raises(WordError):
        preferences.set_reading_system("fr", "poj")
    assert preferences.reading_system("fr") == ""


def test_a_word_saved_in_poj_is_the_tailo_word():
    words.set_status("nan", "食飯", "chia̍h-pn̄g", "learning")
    assert words.status_of("nan", "食飯", "tsia̍h-pn̄g")["status"] == "learning"


def test_card_fields():
    fields = derived_fields("nan", {"word": "食飯", "reading": "tsia̍h-pn̄g", "sentence": "<b>食飯</b>"})
    assert fields["tailo"] == "tsia̍h-pn̄g" and fields["poj"] == "chia̍h-pn̄g"
    assert fields["word_readings"] == "食飯[tsia̍h-pn̄g]"
    assert fields["sentence_readings"].startswith("<b>")
    kept = {"word": "x", "reading": "", "tailo": "kept", "poj": "kept", "word_readings": "kept", "sentence_readings": "kept"}
    assert derived_fields("nan", kept) == {}
    assert derived_fields("fr", {"word": "chat"}) == {}


@needs_taibun
def test_card_fields_from_hanji_only():
    fields = derived_fields("nan", {"word": "食飯", "reading": "", "sentence": "我欲<b>食飯</b>。"})
    assert fields["tailo"] == "tsia̍h-pn̄g"
    assert fields["sentence_readings"] == "我[guá]欲[beh]<b>食飯[tsia̍h-pn̄g]</b>。"


def make_dictionary(path, terms):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Taigi test", "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(terms, ensure_ascii=False))
    return path


NAN_TERMS = [
    ["食飯", "tsia̍h-pn̄g", "", "", 0, ["to eat a meal"], 0, ""],
    ["我", "guá", "", "", 0, ["I, me"], 0, ""],
    ["欲", "beh", "", "", 0, ["to want"], 0, ""],
    ["媠", "", "", "", 0, ["beautiful"], 0, ""],
    ["歹勢", "pháinn-sè", "", "", 0, ["sorry"], 0, ""],
    ["媽祖", "Má-tsóo", "", "", 0, ["Mazu"], 0, ""],
    ["看", "khuànn", "", "", 0, ["to look"], 0, ""],
]


@pytest.fixture
def nan_dict(tmp_path):
    segmentation.clear_cache()
    info = dictionaries.import_dictionary(make_dictionary(tmp_path / "nan.zip", NAN_TERMS))
    yield info
    segmentation.clear_cache()


def test_taigi_dictionary_import_and_lookup(nan_dict):
    assert nan_dict["language"] == "nan"
    assert lookup.lookup("nan", "食飯好")["entries"][0]["expression"] == "食飯"
    # romanized text, in either romanization, finds the Hanji words by their reading
    for text in ("tsia̍h-pn̄g ah", "Chia̍h-pn̄g ah", "tsiah8-png7"):
        entries = lookup.lookup("nan", text)["entries"]
        assert entries and entries[0]["expression"] == "食飯", text


@needs_taibun
def test_lookup_gives_a_reading_to_hanji_only_entries(nan_dict):
    assert lookup.lookup("nan", "媠")["entries"][0]["reading"] == "suí"


def test_colouring_romanized_and_hanji_text(nan_dict):
    words.set_status("nan", "食飯", "tsia̍h-pn̄g", "known")
    text = "Góa beh chia̍h-pn̄g. 我欲食飯 xyz"
    result = segmentation.colour("nan", text)
    assert [w["headword"] for w in result["words"]] == ["我", "欲", "食飯"]
    assert {w["headword"]: w["status"] for w in result["words"]}["食飯"] == "known"
    assert [text[s:s + n] for s, n, _ in result["tokens"]] == ["Góa", "beh", "chia̍h-pn̄g", "我", "欲", "食飯", "xyz"]


@pytest.fixture
def client():
    pytest.importorskip("flask")
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_convert_api(client):
    res = client.post("/api/taigi/convert", json={"text": "chia̍h-pn̄g", "target": "tailo"}, headers=HEADERS)
    assert res.get_json() == {"text": "tsia̍h-pn̄g"}
    res = client.post("/api/taigi/convert", json={"text": "tsia̍h-pn̄g", "target": "tailo", "numbers": True}, headers=HEADERS)
    assert res.get_json() == {"text": "tsiah8-png7"}
    assert client.post("/api/taigi/convert", json={"text": "x", "target": "nope"}, headers=HEADERS).status_code == 400
    assert client.post("/api/taigi/convert", json={"text": "a" * 200_001, "target": "poj"}, headers=HEADERS).status_code == 400


def test_reading_setting_api(client):
    assert client.post("/api/mining/reading", json={"language": "nan", "system": "poj"}, headers=HEADERS).status_code == 200
    assert client.get("/api/mining/languages").get_json()["readings"]["nan"] == "poj"
