import base64
import io
import json
import sqlite3
import types
import urllib.error
import zipfile

import pytest

from miningcat.application import anki
from miningcat.application.mining import dictionaries, lookup, preferences, words
from miningcat.domain.cards import note_type
from miningcat.domain.cards.field_text import plain_field_text
from miningcat.domain.dictionary.deinflection import transformer_for
from miningcat.domain.dictionary.language_guess import guess_dictionary_language
from miningcat.domain.languages import language_key
from miningcat.domain.text import chinese_script
from miningcat.domain.text.chinese_script import ChineseScripts, OpenCcConverter
from miningcat.domain.text.readings import reading_match
from miningcat.domain.text.variants import text_variants
from miningcat.infrastructure import http
from miningcat.infrastructure.persistence.database import Database
from miningcat.infrastructure.persistence.settings_store import settings

from shared import FakeArgos, FakeNllb, FakeOpenCc

pytest.importorskip("flask")

import fake_ankiconnect

HEADERS = {"X-MiningCat": "1"}

# A tiny two-script table so that the tests don't depend on OpenCC.
T2S = dict(zip("說話們國時", "说话们国时"))
S2T = {v: k for k, v in T2S.items()}


@pytest.fixture(autouse=True)
def fake_opencc(monkeypatch):
    monkeypatch.setattr(chinese_script, "chinese_scripts", ChineseScripts(FakeOpenCc(T2S)))


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
    assert language_key("zh-Hant") == "zh"
    assert language_key("zh-HK") == "zh"
    assert language_key("yue-Hant") == "yue"
    assert language_key("ja-JP") == "ja"
    assert language_key("und") == ""


def test_reading_match():
    assert reading_match("huán", "ㄏㄨㄢˊ", "zh") == 2
    assert reading_match("hai2", "hái", "zh") == 2
    assert reading_match("biānr", "ㄅㄧㄢ˙ㄦ", "zh") == 1  # erhua written with a neutral tone
    assert reading_match("hái", "ㄏㄨㄢˊ", "zh") == 0
    assert reading_match("たべる", "タベル", "ja") == 2
    assert reading_match("", "ㄏㄨㄢˊ", "zh") == 0


def test_dictionary_language_guess():
    assert guess_dictionary_language([("食べる", "たべる")]) == "ja"
    assert guess_dictionary_language([("說話", "shuōhuà"), ("我們", "wǒmen")]) == "zh"
    assert guess_dictionary_language([("食飯", "sik6 faan6"), ("我哋", "ngo5 dei6")]) == "yue"
    assert guess_dictionary_language([("사랑", "")]) == "ko"


def test_text_variants():
    assert "たべる" in text_variants("タベル", "ja")
    assert "ガ" in text_variants("ｶﾞ", "ja")  # half width becomes full width
    assert "l'homme" in text_variants("L’homme", "fr")


def test_chinese_scripts():
    assert chinese_script.chinese_script("說話") == "traditional"
    assert chinese_script.chinese_script("说话") == "simplified"
    assert chinese_script.chinese_script("說话") == "mixed"
    assert chinese_script.chinese_script("天氣") in ("both", "traditional")
    assert chinese_script.chinese_counterpart("說話") == ("simplified", "说话")
    assert chinese_script.chinese_counterpart("我") is None


# With the real OpenCC tables: characters valid in both scripts don't make a word simplified.
def test_chinese_scripts_with_opencc():
    pytest.importorskip("opencc")
    scripts = ChineseScripts(OpenCcConverter())
    if not any(scripts.converter.tables()):
        pytest.skip("OpenCC character tables not available")
    assert scripts.script("了解") == "both"
    assert scripts.script("里面") == "both"
    assert scripts.script("台灣") == "traditional"
    assert scripts.script("说话") == "simplified"
    assert scripts.counterpart("里边") == ("traditional", "裡邊")
    assert scripts.counterpart("说话", "yue") == ("traditional", "説話")


def test_script_detection_without_tables():
    scripts = ChineseScripts(FakeOpenCc(T2S, tables=(set(), set())))
    assert scripts.script("說話") == "traditional"
    assert scripts.script("说话") == "simplified"
    assert scripts.script("我") == "both"


def test_words_in_both_scripts_keep_their_form():
    preferences.set_chinese_script_preference("zh", "traditional")
    assert words.preferred_form("zh", "说话") == "說話"
    assert words.preferred_form("zh", "我們") == "我們"
    assert words.preferred_form("zh", "天氣") == "天氣"
    preferences.set_chinese_script_preference("zh", "simplified")
    assert words.preferred_form("zh", "說話") == "说话"
    assert words.preferred_form("zh", "天") == "天"


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


def test_words_sorted_by_date_added():
    # an Anki note's id is its creation time (ms): the word was added then, not when it was synced
    words.set_status("zh", "早", "zǎo", "learning", source="anki", anki_note_id=1_600_000_000_000)
    words.set_status("zh", "晚", "wǎn", "learning")
    words.set_status("zh", "中", "zhōng", "learning", source="anki", anki_note_id=1_700_000_000_000)
    assert [w["expression"] for w in words.list_words("zh", order="added")] == ["晚", "中", "早"]
    assert [w["expression"] for w in words.list_words("zh", order="added_asc")] == ["早", "中", "晚"]
    assert words.list_words("zh", order="added_asc")[0]["added"] == 1_600_000_000


def test_other_script_is_linked():
    words.set_status("zh", "说话", "shuōhuà", "known")
    status = words.status_of("zh", "說話", "shuōhuà")
    assert status["status"] == "new"
    assert status["linked"] == {"script": "simplified", "expression": "说话", "status": "known"}


def test_script_preference(zh_dict):
    assert words.preferred_form("zh", "说话") == "说话"
    preferences.set_chinese_script_preference("zh", "traditional")
    assert words.preferred_form("zh", "说话") == "說話"
    entry = next(e for e in lookup.lookup("zh", "说话")["entries"] if e["expression"] == "说话")
    assert entry["form"] == "說話"
    with pytest.raises(words.WordError):
        preferences.set_chinese_script_preference("ja", "traditional")


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
        "Hanzi": "{word}", "Zhuyin": "{zhuyin}", "Meaning": "{definition}", "Sentence": "{sentence}",
        "Picture": "{image}", "Sentence Audio": "{sentence_audio}"}
    assert anki.guess_field_templates(["Front", "Back"]) == {"Front": "{word}", "Back": "{definition}"}
    assert anki.guess_field_templates(["A", "B"]) == {"A": "{word}", "B": "{definition}"}
    assert anki.guess_field_templates(["Word", "Translation"]) == {"Word": "{word}", "Translation": "{definition}"}


# Note types where "Translation" is the sentence's, the definition goes to "Definitions".
def test_guess_field_templates_with_a_sentence_translation_field():
    fields = ["Sentence", "Translation", "Target Word", "Definitions", "Screenshot", "Sentence Audio",
              "Word Audio", "Images", "Example Sentences", "Zhuyin", "Is Vocabulary Card"]
    assert anki.guess_field_templates(fields) == {
        "Sentence": "{sentence}", "Translation": "{sentence_translation}", "Target Word": "{word}",
        "Definitions": "{definition}", "Screenshot": "{image}", "Sentence Audio": "{sentence_audio}",
        "Word Audio": "{audio}", "Images": "", "Example Sentences": "", "Zhuyin": "{zhuyin}",
        "Is Vocabulary Card": ""}


def test_guess_field_templates_of_miningcat_note_type():
    fields = note_type.FIELDS + ["My field"]
    zh = anki.guess_field_templates(fields, "zh")
    assert zh["Word"] == "{word}" and zh["Word with reading"] == "{word_readings}"
    assert zh["Sentence"] == "{sentence_readings}" and zh["Language"] == "{language}"
    assert zh["My field"] == ""
    fr = anki.guess_field_templates(fields, "fr")
    assert fr["Sentence"] == "{sentence}" and fr["Word with reading"] == ""
    assert anki.guess_field_templates(["Expression", "Lang"])["Lang"] == "{language}"


def test_note_type_templates():
    templates = note_type.templates({"zh": "zhuyin"})
    assert '"zh": "zhuyin"' in templates["front"] and "__OPTIONS__" not in templates["back"]
    for name in note_type.FIELDS:
        assert "{{" + name + "}}" in templates["front"] + templates["back"]


def test_deck_is_created(fake_anki):
    assert anki.create_deck("ja") == {"deck": "Japanese - MiningCat"}
    preferences.set_chinese_script_preference("zh", "traditional")
    assert anki.create_deck("zh") == {"deck": "Mandarin (traditional) - MiningCat"}
    assert anki.create_deck("zh") == {"deck": "Mandarin (traditional) - MiningCat"}  # already there: kept
    preferences.set_chinese_script_preference("zh", "both")
    assert anki.create_deck("zh")["deck"] == "Mandarin - MiningCat"
    assert {"Japanese - MiningCat", "Mandarin (traditional) - MiningCat"} <= set(anki.status()["decks"])


def test_note_type_is_created_then_updated(fake_anki):
    result = anki.install_note_type("zh")
    assert result["model"] == "MiningCat" and fake_anki.models["MiningCat"] == note_type.FIELDS
    assert result["templates"]["Sentence"] == "{sentence_readings}"
    assert "mc-readings" in fake_anki.templates["MiningCat"]["templates"]["Recognition"]["Back"]
    # an older one (the .apkg's first note type) gets the fields it lacks, the user's own are kept
    fake_anki.models["MiningCat"] = ["Word", "Reading", "Definition", "Sentence", "My field"]
    fake_anki.templates["MiningCat"]["css"] = "old"
    result = anki.install_note_type("fr")
    assert fake_anki.models["MiningCat"][:5] == ["Word", "Reading", "Definition", "Sentence", "My field"]
    assert set(note_type.FIELDS) <= set(fake_anki.models["MiningCat"])
    assert result["templates"]["My field"] == "" and result["templates"]["Sentence"] == "{sentence}"
    assert fake_anki.templates["MiningCat"]["css"] != "old"


def test_card_is_sent_to_miningcat_note_type(fake_anki):
    preferences.set_chinese_script_preference("zh", "traditional")
    setup = anki.install_note_type("zh")
    anki.save_config({"notes": {"zh": {"deck": "Mining::Chinese", "model": setup["model"], "fields": setup["templates"]}}})
    card = anki.create_card("zh", {"word": "公園", "reading": "gōngyuán", "definition": "park", "sentence": "去<b>公園</b>"}, {})
    fields = fake_anki.notes[card["anki_note_id"]]["fields"]
    assert fields["Word"] == "公園" and fields["Word with reading"] == "公園[gong1 yuan2]"
    assert fields["Sentence"].startswith("去") and "<b>公園[gong1 yuan2]</b>" in fields["Sentence"]
    assert fields["Language"] == "zh-Hant"


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


# Word audio from Wiktionary is a link: MiningCat downloads it (Anki downloading every link gets refused by
# Wikimedia during a big import) and sends the file.
def test_card_is_sent_with_linked_audio(fake_anki, monkeypatch):
    setup_chinese_notes()
    audio_url = "https://upload.wikimedia.org/wikipedia/commons/transcoded/e/e4/Zh-zh%C5%8Dngy%C4%81ng.oga/Zh-zh%C5%8Dngy%C4%81ng.oga.mp3"
    monkeypatch.setattr(http, "get", lambda url, timeout=8: b"ID3 audio")
    card = anki.create_card("zh", {"word": "中央", "definition": "center"}, {"audio": {"url": audio_url}})
    assert card["status"] == "sent", card["error"]
    assert fake_anki.media[card["media"]["audio"]["filename"]] == {"data": base64.b64encode(b"ID3 audio").decode()}
    downloaded = anki.card_media_dir() / card["media"]["audio"]["filename"]
    assert downloaded.exists()
    anki.delete_card(card["id"])
    assert not downloaded.exists()


def test_card_waits_when_its_audio_cant_be_downloaded(fake_anki, monkeypatch):
    setup_chinese_notes()

    def refused(url, timeout=8):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(http, "get", refused)
    card = anki.create_card("zh", {"word": "中央", "definition": "center"}, {"audio": {"url": "https://upload.wikimedia.org/a.mp3"}})
    assert card["status"] == "pending" and "next sync" in card["error"]
    monkeypatch.setattr(http, "get", lambda url, timeout=8: b"ID3")
    assert anki.send_pending() == {"sent": 1, "failed": 0, "pending": 0}


def test_wikimedia_refusals_are_retried(monkeypatch):
    calls, waits = [], []

    class Answer:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"audio"

    def urlopen(request, timeout, context):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "5"}, None)
        return Answer()
    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(http.time, "sleep", waits.append)
    assert http.get("https://upload.wikimedia.org/a.mp3") == b"audio"
    assert len(calls) == 3 and [w for w in waits if w >= 5] == [5, 5]  # the Retry-After asked for

    calls.clear()
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda r, timeout, context: (_ for _ in ()).throw(urllib.error.HTTPError(r.full_url, 404, "Not Found", {}, None)))
    with pytest.raises(urllib.error.HTTPError):
        http.get("https://upload.wikimedia.org/b.mp3")  # a missing file isn't retried


def test_same_sentence_of_another_word_isnt_a_duplicate(fake_anki):
    # Migaku's note type starts with the sentence, the only field Anki compares
    fake_anki.models["Migaku"] = ["Sentence", "Target Word"]
    anki.save_config({"notes": {"zh": {"deck": "Mining::Chinese", "model": "Migaku",
                                       "fields": {"Sentence": "{sentence}", "Target Word": "{word}"}}}})
    sentence = "感冒一定愛配溫開水"
    assert anki.create_card("zh", {"word": "開水", "sentence": sentence}, {})["status"] == "sent"
    assert anki.create_card("zh", {"word": "配", "sentence": sentence}, {})["status"] == "sent"
    again = anki.create_card("zh", {"word": "配", "sentence": sentence}, {})
    assert again["status"] == "failed" and "duplicate" in again["error"]


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
    assert plain_field_text("<b>漢字</b>&nbsp;") == "漢字"
    assert plain_field_text("漢字[かんじ]") == "漢字"
    assert plain_field_text("[sound:a.mp3]word") == "word"


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
        collection = tmp_path / "collection.anki2"
        collection.write_bytes(z.read("collection.anki2"))
    with sqlite3.connect(collection) as db:
        note = db.execute("select flds from notes").fetchone()[0].split("\x1f")
    fields = dict(zip(note_type.FIELDS, note))
    assert fields["Word"] == "公園" and fields["Word with reading"] == "公園[gong1 yuan2]"
    assert fields["Word audio"] == f"[sound:{card['media']['audio']['filename']}]" and fields["Language"].startswith("zh")
    assert anki.get_card(card["id"])["status"] == "exported"
    with pytest.raises(anki.AnkiError, match="no cards"):
        anki.export_apkg()


# ---------------------------------------------------------------- HTTP API

@pytest.fixture
def client(tmp_path):
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_http_lookup_status_and_cards(client, zh_dict, fake_anki):
    res = client.post("/api/dict/lookup", json={"language": "zh-Hant", "text": "說話"}, headers=HEADERS).get_json()
    assert res["language"] == "zh" and res["entries"][0]["expression"] == "說話"
    assert client.post("/api/dict/lookup", json={"language": "klingon", "text": "x"}, headers=HEADERS).status_code == 400
    # a known reading (a CSV import) tells the entry of that pronunciation
    entry = client.post("/api/dict/lookup", json={"language": "zh", "text": "說話", "reading": "shuo1hua4"}, headers=HEADERS).get_json()["entries"][0]
    assert entry["reading_match"] == 2
    entry = client.post("/api/dict/lookup", json={"language": "zh", "text": "說話", "reading": "shuòhuà"}, headers=HEADERS).get_json()["entries"][0]
    assert entry["reading_match"] == 1

    assert client.post("/api/words/status", json={"language": "zh", "expression": "說話", "reading": "shuōhuà", "status": "known"},
                       headers=HEADERS).get_json() == {"status": "known"}
    assert client.get("/api/words?language=zh").get_json()["words"][0]["expression"] == "說話"
    assert client.post("/api/words/statuses", json={"language": "zh", "expressions": ["說話", "x"]}, headers=HEADERS).get_json() == {"statuses": {"說話": "known"}}

    setup_chinese_notes()
    card = client.post("/api/cards", json={"language": "zh", "fields": {"word": "我們", "definition": "we"}}, headers=HEADERS).get_json()["card"]
    assert card["status"] == "sent"
    assert client.get("/api/cards?status=sent").get_json()["cards"][0]["expression"] == "我們"
    assert client.get("/api/anki/status").get_json()["connected"] is True
    assert client.post("/api/anki/deck", json={"language": "zh"}, headers=HEADERS).get_json()["deck"].endswith(" - MiningCat")
    installed = client.post("/api/anki/note-type", json={"language": "zh"}, headers=HEADERS).get_json()
    assert installed["model"] == "MiningCat"
    assert client.get("/api/anki/fields?model=MiningCat&language=zh").get_json()["guess"]["Sentence"] == "{sentence_readings}"
    fields = client.get("/api/anki/fields?model=Basic").get_json()
    assert fields["guess"] == {"Front": "{word}", "Back": "{definition}"}
    assert client.get("/settings/").status_code == 302  # no language studied yet: the home page asks for it
    client.post("/api/profile", json={"language": "zh"}, headers=HEADERS)
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


# ---------------------------------------------------------------- word colours (segmentation)

from miningcat.application.mining import segmentation


@pytest.fixture(autouse=True)
def _fresh_segmentation():
    segmentation.clear_cache()
    yield
    segmentation.clear_cache()


def words_of(language, text):
    return [(text[start:start + length], headword) for start, length, headword in segmentation.segment(language, text)]


def test_chinese_longest_words(zh_dict):
    assert words_of("zh", "我們說話，他說。") == [("我們", "我們"), ("說話", "說話"), ("他", None), ("說", "說")]


def test_no_word_spans_two_paragraphs(zh_dict):
    assert words_of("zh", "我\n們") == [("我", None), ("們", None)]


def test_japanese_deinflection_and_rare_words(tmp_path):
    terms = [
        ["食べる", "たべる", "v1", "v1", 100, ["to eat"], 1, ""],
        ["名前", "なまえ", "n", "", 100, ["name"], 2, ""],
        ["は", "は", "prt", "", 100, ["topic"], 3, ""],
        ["未だ", "まだ", "1 adv uk", "", 100, ["yet"], 4, ""],
        ["浜", "はま", "1 n", "", 100, ["beach"], 5, ""],
        ["浜", "はま", "2 n uk", "", 100, ["beach (kana)"], 5, ""],
        ["はま", "はま", "n", "", -500, ["rare word"], 6, ""],
        ["ハマ", "ハマ", "n", "", 100, ["Hama"], 7, ""],
        ["無い", "ない", "adj-i", "adj-i", 100, ["nonexistent"], 8, ""],
        ["だ", "だ", "cop", "", 100, ["copula"], 9, ""],
    ]
    dictionaries.import_dictionary(make_dictionary(tmp_path / "ja.zip", "JMdict", terms))
    # まだ (usually kana) beats the rare はま, and hiragana は+ま isn't the katakana word ハマ
    assert words_of("ja", "名前はまだ無い") == [("名前", "名前"), ("は", "は"), ("まだ", "未だ"), ("無い", "無い")]
    assert words_of("ja", "食べていた")[0] == ("食べていた", "食べる")


def test_words_with_spaces_and_expressions(tmp_path):
    terms = [
        ["manger", "", "v", "v", 0, ["to eat"], 1, ""],
        ["pomme de terre", "", "n", "", 0, ["potato"], 2, ""],
        ["pomme", "", "n", "", 0, ["apple"], 3, ""],
    ]
    dictionaries.import_dictionary(make_dictionary(tmp_path / "fr.zip", "Wiktionnaire", terms), language="fr")
    assert words_of("fr", "Nous mangeons une pomme de terre. Pomme\nde terre") == [
        ("Nous", None), ("mangeons", "manger"), ("une", None), ("pomme de terre", "pomme de terre"),
        ("Pomme", "pomme"), ("de", None), ("terre", None)]


def test_segmentation_follows_dictionary_changes(tmp_path, zh_dict):
    assert words_of("zh", "說話") == [("說話", "說話")]
    dictionaries.update_dictionary(zh_dict["id"], enabled=False)
    assert words_of("zh", "說話") == []


def test_colours_use_the_saved_form(zh_dict):
    preferences.set_chinese_script_preference("zh", "traditional")
    words.set_status("zh", "說話", "", "learning")
    result = segmentation.colour("zh", "说话，说话")
    assert result["words"] == [{"headword": "说话", "form": "說話", "status": "learning", "rank": None}]
    assert result["tokens"] == [[0, 2, 0], [3, 2, 0]]


def test_http_segment(client, zh_dict):
    words.set_status("zh", "我們", "", "known")
    res = client.post("/api/words/segment", json={"language": "zh-Hant", "text": "我們說話"}, headers=HEADERS).get_json()
    assert res["language"] == "zh"
    assert [w["status"] for w in res["words"]] == ["known", "new"]
    assert client.post("/api/words/segment", json={"language": "zh", "text": 3}, headers=HEADERS).status_code == 400
    assert client.post("/api/words/segment", json={"language": "zh", "text": "x" * (2_000_001)}, headers=HEADERS).status_code == 400


# ---------------------------------------------------------------- zhuyin

from miningcat.domain.text.zhuyin import pinyin_to_zhuyin, zhuyin_to_pinyin


@pytest.mark.parametrize("pinyin, zhuyin", [
    ("zhōngguó", "ㄓㄨㄥ ㄍㄨㄛˊ"),
    ("xī'ān", "ㄒㄧ ㄢ"),
    ("xiān", "ㄒㄧㄢ"),
    ("lǜ", "ㄌㄩˋ"),
    ("lǚyóu", "ㄌㄩˇ ㄧㄡˊ"),
    ("xué", "ㄒㄩㄝˊ"),
    ("wǒmen", "ㄨㄛˇ ˙ㄇㄣ"),
    ("zhīdào", "ㄓ ㄉㄠˋ"),
    ("nǚ'ér", "ㄋㄩˇ ㄦˊ"),
    ("yīhuìr", "ㄧ ㄏㄨㄟˋㄦ"),
    ("yīxiàr5", "ㄧ ㄒㄧㄚˋㄦ"),  # CC-CEDICT's erhua
    ("shuo1 hua4", "ㄕㄨㄛ ㄏㄨㄚˋ"),
    ("lu:4", "ㄌㄩˋ"),  # CC-CEDICT's ü
    ("ㄕㄨㄛ ㄏㄨㄚˋ", "ㄕㄨㄛ ㄏㄨㄚˋ"),
    ("Zhōngguó", "ㄓㄨㄥ ㄍㄨㄛˊ"),
    ("Wáng Xiǎo·míng", "ㄨㄤˊ ㄒㄧㄠˇ ㄇㄧㄥˊ"),
    ("yī ge , liǎng ge", "ㄧ ˙ㄍㄜ , ㄌㄧㄤˇ ˙ㄍㄜ"),
    ("xing2dong4", "ㄒㄧㄥˊ ㄉㄨㄥˋ"),
    ("ni3hao", "ㄋㄧˇ ˙ㄏㄠ"),  # no tone: neutral
    ("Xīān", "ㄒㄧ ㄢ"),  # two tone marks: two syllables, even without the apostrophe
    ("fangan", "˙ㄈㄢ ˙ㄍㄢ"),  # without an apostrophe, a syllable can't start with a, o or e
    ("fang'an", "˙ㄈㄤ ˙ㄢ"),
    ("hua1r", "ㄏㄨㄚㄦ"), ("huar1", "ㄏㄨㄚㄦ"), ("jīnrgè", "ㄐㄧㄣㄦ ㄍㄜˋ"),
    ("kèrén", "ㄎㄜˋ ㄖㄣˊ"), ("pòkérì", "ㄆㄛˋ ㄎㄜˊ ㄖˋ"),  # an r before a vowel is an initial, not erhua
    ("hm5", "˙ㄏㄇ"), ("ng2", "ㄫˊ"),
])
def test_pinyin_to_zhuyin(pinyin, zhuyin):
    assert pinyin_to_zhuyin(pinyin) == zhuyin


@pytest.mark.parametrize("pinyin", ["", "hello world!", "xx5", "qqq", "CP", "2xing", "xing0"])
def test_not_pinyin(pinyin):
    assert pinyin_to_zhuyin(pinyin) == ""


@pytest.mark.parametrize("zhuyin, pinyin", [
    ("ㄒㄧㄥˊ ㄉㄨㄥˋ", "xíng dòng"),
    ("˙ㄌㄜ", "le"),
    ("ㄉㄚˋㄢ", "dà'ān"),
    ("ㄋㄩˇㄦˊ", "nǚ'ér"),
    ("ㄏㄨㄚㄦ", "huār"),
    ("ㄓㄜˋㄦ", "zhèr"),
    ("ㄅㄚㄦˇㄍㄢˋ", "bā'ěrgàn"),      # a toned ㄦ is 爾 itself, not erhua
    ("ㄌㄠˇㄖㄣˊ", "lǎorén"),         # the r of 人 isn't erhua
    ("˙ㄉㄜㄑㄧˇ", "deqǐ"),           # a neutral tone inside a word
    ("˙ㄅㄛ˙ㄅㄛㄇㄧˇ", "bobomǐ"),     # Taiwan's dot, before its syllable
    ("ㄇㄚ ˙ㄌㄡ", "mā lou"),
    ("ㄖㄣˋㄕ˙ ㄇㄚ˙", "rènshi ma"),   # dots after their syllables, at the end of words
    ("ㄅㄞㄅㄞ", "bāibāi"),            # no mark: first tone
    ("ㄐㄩㄝˊㄉㄧㄥˋ", "juédìng"), ("ㄌㄩㄝˋ", "lüè"), ("ㄧㄥㄒㄩㄥˊ", "yīngxióng"),
    ("ㄓ", "zhī"), ("ㄕˋ", "shì"), ("ㄌㄧㄡˊ", "liú"), ("ㄍㄨㄟˇ", "guǐ"), ("ㄇˊ", "ḿ"), ("˙ㄫㄐㄧㄥˋ", "ngjìng"),
])
def test_zhuyin_to_pinyin(zhuyin, pinyin):
    assert zhuyin_to_pinyin(zhuyin) == pinyin


@pytest.mark.parametrize("text", ["xíng", "", "CP", "ㄅㄅㄅ", "ㆠㄚ"])
def test_not_zhuyin(text):
    assert zhuyin_to_pinyin(text) == ""


@pytest.mark.parametrize("tone", [1, 2, 3, 4, 5])
def test_every_syllable_both_ways(tone):
    from miningcat.domain.text.zhuyin import ZHUYIN_OF

    for syllable in ZHUYIN_OF:
        numbered = f"{syllable}{tone}"
        zhuyin = pinyin_to_zhuyin(numbered)
        assert zhuyin, numbered
        assert pinyin_to_zhuyin(zhuyin_to_pinyin(zhuyin)) == zhuyin, numbered


def test_readings_shown_in_the_chosen_system():
    preferences.set_reading_system("zh", "pinyin")
    assert words.display_reading("zh", "行", "ㄒㄧㄥˊ") == "xíng"  # a zhuyin dictionary, read in pinyin
    preferences.set_reading_system("zh", "zhuyin")
    assert words.display_reading("zh", "行", "xing2") == "ㄒㄧㄥˊ"
    assert words.display_reading("zh", "行", "ㄒㄧㄥˊ") == "ㄒㄧㄥˊ"


def test_zhuyin_field_of_a_card():
    setup = {"fields": {"Hanzi": "{word}", "Zhuyin": "{zhuyin}"}}
    fields = {"word": "說話", "reading": "shuōhuà"}
    assert anki.note_fields(setup, fields, {}, "zh") == {"Hanzi": "說話", "Zhuyin": "ㄕㄨㄛ ㄏㄨㄚˋ"}
    assert anki.note_fields(setup, fields, {}, "ja")["Zhuyin"] == ""


# ---------------------------------------------------------------- Korean

from miningcat.domain.text import hangul


@pytest.mark.parametrize("text, jamo", [
    ("한글", "ㅎㅏㄴㄱㅡㄹ"), ("와", "ㅇㅗㅏ"), ("값", "ㄱㅏㅂㅅ"), ("먹었다", "ㅁㅓㄱㅇㅓㅆㄷㅏ"), ("ㄳ ㅘ a", "ㄱㅅ ㅗㅏ a"),
])
def test_hangul_round_trip(text, jamo):
    assert hangul.disassemble(text) == jamo
    assert hangul.assemble(jamo) == text


def test_hangul_assembles_partial_jamo():
    assert hangul.assemble("ㅁㅓㄱㄷㅏ") == "먹다"
    assert hangul.assemble("ㄱㅏㅂㅅㅇㅣ") == "값이"
    assert hangul.assemble("ㅗㅏ") == "ㅘ"
    assert hangul.assemble("ㄹㄱ") == "ㄺ"


def test_korean_deinflection():
    transformer = transformer_for("ko")
    for inflected, base in (("먹었다", "먹다"), ("갔어요", "가다"), ("예뻤다", "예쁘다"), ("공부했습니다", "공부하다")):
        assert base in {d.text for d in transformer.transform(inflected)}


@pytest.fixture
def ko_dict(tmp_path):
    terms = [
        ["친구", "", "n", "n", 0, ["friend"], 1, ""],
        ["밥", "", "n", "n", 0, ["rice"], 2, ""],
        ["밥다", "", "v dialect", "v", 0, ["(dialect) a verb"], 3, ""],
        ["먹다", "", "v", "v", 0, ["to eat"], 4, ""],
        ["와", "", "intj", "intj", 0, ["wow"], 5, ""],
    ]
    return dictionaries.import_dictionary(make_dictionary(tmp_path / "ko.zip", "Korean", terms), language="ko")


def test_korean_segmentation_splits_particles(ko_dict):
    assert words_of("ko", "친구와 밥을 먹었어요") == [("친구", "친구"), ("밥", "밥"), ("먹었어요", "먹다")]


def test_korean_lookup_finds_the_word_before_its_particle(ko_dict):
    entries = lookup.lookup("ko", "친구와 같이")["entries"]
    assert entries[0]["expression"] == "친구"
    entries = lookup.lookup("ko", "먹었어요")["entries"]
    assert entries[0]["expression"] == "먹다" and entries[0]["inflections"]


# ---------------------------------------------------------------- character dictionaries

def make_kanji_dictionary(path, title, rows, meta=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": title, "revision": "1", "format": 3}))
        z.writestr("kanji_bank_1.json", json.dumps(rows, ensure_ascii=False))
        if meta:
            z.writestr("kanji_meta_bank_1.json", json.dumps(meta, ensure_ascii=False))
    return path


def test_kanji_dictionary_import_and_lookup(tmp_path, ja_dict):
    path = make_kanji_dictionary(tmp_path / "kanji.zip", "KANJIDIC", [
        ["食", "ショク ジキ", "く.う た.べる", "jouyou", ["eat", "food"], {"strokes": "9", "grade": "2", "skip": "2-2-7"}],
        ["食べ物", "", "", "", ["a whole word: skipped"], {}],
    ], meta=[["食", "freq", 328]])
    info = dictionaries.import_dictionary(path)
    assert info["language"] == "ja" and info["kanji_count"] == 1 and info["term_count"] == 0
    entry = lookup.lookup("ja", "食べる")["entries"][0]
    assert entry["characters"] == [{"character": "食", "entries": [{
        "dictionary": "KANJIDIC", "onyomi": ["ショク", "ジキ"], "kunyomi": ["く.う", "た.べる"], "meanings": ["eat", "food"],
        "stats": {"strokes": "9", "grade": "2"}, "frequencies": ["KANJIDIC 328"]}]}]
    dictionaries.delete_dictionary(info["id"])
    assert lookup.lookup("ja", "食べる")["entries"][0]["characters"] == []


def test_hanzi_dictionary_language_from_pinyin(tmp_path):
    path = make_kanji_dictionary(tmp_path / "hanzi.zip", "Hanzi", [["說", "shuō", "", "", ["to speak"], {}], ["話", "huà", "", "", ["speech"], {}]])
    assert dictionaries.inspect(path)["language"] == "zh"


def test_empty_dictionary_is_refused(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Empty", "revision": "1", "format": 3, "sourceLanguage": "ja"}))
    with pytest.raises(dictionaries.DictionaryError, match="no terms"):
        dictionaries.import_dictionary(path)


def test_old_databases_get_new_columns(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE dictionaries (id INTEGER PRIMARY KEY, title TEXT NOT NULL, revision TEXT, language TEXT NOT NULL,"
                 " target_language TEXT, author TEXT, url TEXT, description TEXT, attribution TEXT, enabled INTEGER NOT NULL DEFAULT 1,"
                 " priority INTEGER NOT NULL DEFAULT 0, term_count INTEGER NOT NULL DEFAULT 0, meta_count INTEGER NOT NULL DEFAULT 0,"
                 " imported REAL NOT NULL)")
    conn.commit()
    conn.close()
    with Database(lambda: path).session() as conn:
        assert "kanji_count" in {row[1] for row in conn.execute("PRAGMA table_info(dictionaries)")}


# ---------------------------------------------------------------- pronunciations and word audio

def test_pitch_and_ipa_in_lookups(tmp_path, ja_dict):
    path = tmp_path / "pitch.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Pitch", "revision": "1", "format": 3, "sourceLanguage": "ja"}))
        z.writestr("term_meta_bank_1.json", json.dumps([
            ["食べる", "pitch", {"reading": "たべる", "pitches": [{"position": 2}, {"position": "LHL"}]}],
            ["食べる", "pitch", {"reading": "くべる", "pitches": [{"position": 0}]}],
            ["食べる", "ipa", {"reading": "たべる", "transcriptions": [{"ipa": "[ta̠bɛ̝ɾɯ̟ᵝ]"}]}],
        ], ensure_ascii=False))
    dictionaries.import_dictionary(path)
    entry = lookup.lookup("ja", "食べる")["entries"][0]
    assert entry["pronunciations"] == [
        {"dictionary": "Pitch", "reading": "たべる", "pitches": [2, "LHL"]},
        {"dictionary": "Pitch", "reading": "たべる", "ipa": ["[ta̠bɛ̝ɾɯ̟ᵝ]"]},
    ]


import urllib.parse

from miningcat.application.mining import translation, word_audio
from miningcat.infrastructure.word_audio.japanesepod101 import JapanesePod101Source
from miningcat.infrastructure.word_audio.wikimedia import is_language_file


@pytest.fixture
def fake_web(monkeypatch):
    """Answers word_audio's requests from a table: {url prefix: bytes or dict}."""
    answers = {}

    def get(url, params=None):
        full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        for prefix, answer in answers.items():
            if prefix in full:
                if isinstance(answer, Exception):
                    raise answer
                return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        return json.dumps({}).encode()

    monkeypatch.setattr(word_audio, "finder", word_audio.WordAudioFinder(get))
    return answers


def test_japanesepod101_skips_its_missing_clip(fake_web, monkeypatch):
    import hashlib
    fake_web["languagepod101"] = b"real audio"
    assert word_audio.sources("ja", "食べる", "たべる")[0]["name"] == "JapanesePod101"
    missing = b"missing clip"
    monkeypatch.setattr(JapanesePod101Source, "MISSING_SHA256", hashlib.sha256(missing).hexdigest())
    fake_web["languagepod101"] = missing
    word_audio.finder.clear_cache()
    assert word_audio.sources("ja", "食べる", "たべる") == []


def test_wiktionary_and_lingua_libre(fake_web):
    fake_web["prop=images"] = {"query": {"pages": {"1": {"images": [
        {"title": "File:Fr-manger.ogg"}, {"title": "File:en-uk-manger.ogg"}, {"title": "File:Manger.jpg"}]}}}}
    fake_web["list=search"] = {"query": {"search": [
        {"title": "File:LL-Q150 (fra)-Pamputt-manger.wav"}, {"title": "File:LL-Q150 (fra)-Pamputt-manger des pommes.wav"},
        {"title": "File:LL-Q1860 (eng)-X-manger.wav"}]}}
    fake_web["prop=imageinfo"] = {"query": {"pages": {
        "1": {"title": "File:Fr-manger.ogg", "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/9/90/Fr-manger.ogg"}]},
        "2": {"title": "File:LL-Q150 (fra)-Pamputt-manger.wav",
              "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/1/19/LL-Q150_%28fra%29-Pamputt-manger.wav?utm=x"}]}}}}
    assert word_audio.sources("fr", "manger") == [
        {"name": "Wiktionary", "url": "https://upload.wikimedia.org/wikipedia/commons/transcoded/9/90/Fr-manger.ogg/Fr-manger.ogg.mp3"},
        {"name": "Lingua Libre (Pamputt)",
         "url": "https://upload.wikimedia.org/wikipedia/commons/transcoded/1/19/LL-Q150_%28fra%29-Pamputt-manger.wav/LL-Q150_%28fra%29-Pamputt-manger.wav.mp3"},
    ]


def test_mandarin_audio_excludes_other_chinese_languages():
    assert is_language_file("File:Zh-xièxie.ogg", "zh")
    assert not is_language_file("File:Zh-wuu-謝謝.opus", "zh")
    assert is_language_file("File:Zh-yue-你好.opus", "yue")


def test_mandarin_audio_of_the_reading():
    from miningcat.application.mining.word_audio import _for_reading
    found = [{"name": "Wiktionary", "url": "https://x/Zh-zh%C3%B2ng.ogg/Zh-zh%C3%B2ng.ogg.mp3"},
             {"name": "Lingua Libre", "url": "https://x/LL-Q9192_%28cmn%29-A-%E4%B8%AD.wav/LL-Q9192_%28cmn%29-A-%E4%B8%AD.wav.mp3"},
             {"name": "Wiktionary", "url": "https://x/Zh-zh%C5%8Dng.ogg/Zh-zh%C5%8Dng.ogg.mp3"}]
    # 中 zhōng: its recording first, zhòng's left out, the one named after the characters kept
    assert [s["url"] for s in _for_reading(found, "ㄓㄨㄥ")] == [found[2]["url"], found[1]["url"]]


def test_offline_audio_is_retried(fake_web):
    import urllib.error
    fake_web["wiktionary"] = urllib.error.URLError("offline")
    fake_web["commons"] = urllib.error.URLError("offline")
    assert word_audio.sources("ko", "먹다") == []
    assert not word_audio.finder.is_cached("ko", "먹다")


def test_http_word_audio(client, monkeypatch):
    monkeypatch.setattr(word_audio, "sources", lambda language, expression, reading: [{"name": "X", "url": f"https://x/{expression}"}])
    assert client.get("/api/dict/audio?language=fr&expression=manger").get_json() == {"sources": [{"name": "X", "url": "https://x/manger"}]}
    assert client.get("/api/dict/audio?language=fr").status_code == 400


def test_tts_voices_by_language():
    from miningcat.application.mining import sentence_tts
    zh = sentence_tts.voices("zh")
    assert zh["default"] == "zh-TW-HsiaoChenNeural" and "zh-CN-XiaoxiaoNeural" in [v["id"] for v in zh["voices"]]
    assert [v["id"] for v in sentence_tts.voices("yue")["voices"]][0].startswith("zh-HK-")
    assert sentence_tts.voices("ru") == {"voices": [], "default": ""}


def test_http_sentence_tts(client, monkeypatch):
    from miningcat.application.mining import sentence_tts

    monkeypatch.setattr(sentence_tts, "tts", types.SimpleNamespace(synthesize=lambda text, voice: f"{voice}:{text}".encode()))
    assert client.get("/api/tts/voices?language=ja").get_json()["default"] == "ja-JP-NanamiNeural"
    res = client.post("/api/tts", json={"language": "zh", "text": " 位處大陸\n中央 ", "voice": "zh-TW-YunJheNeural"}, headers=HEADERS)
    assert res.status_code == 200
    assert base64.b64decode(res.get_json()["data"].split(",", 1)[1]) == "zh-TW-YunJheNeural:位處大陸 中央".encode()
    assert client.post("/api/tts", json={"language": "zh", "text": "x", "voice": "ja-JP-NanamiNeural"}, headers=HEADERS).status_code == 400
    assert client.post("/api/tts", json={"language": "zh", "text": "  ", "voice": "zh-TW-YunJheNeural"}, headers=HEADERS).status_code == 400


def test_default_tag_is_mining_cat():
    anki.save_config({"notes": {"zh": {"deck": "D", "model": "M", "fields": {}}}})
    assert anki.get_config()["notes"]["zh"]["tags"] == "mining-cat"
    # cards set up with the old default tag get the new one
    config = anki.get_config()
    config["notes"]["zh"]["tags"] = "miningcat"
    settings.set("anki", config)
    assert anki.get_config()["notes"]["zh"]["tags"] == "mining-cat"


def test_sentence_voice_from_settings(client):
    from miningcat.application.mining import sentence_tts
    assert sentence_tts.default_voice("zh") == "zh-TW-HsiaoChenNeural"
    anki.save_config({"tts_voices": {"zh": "zh-CN-YunxiNeural", "ja": ""}})
    assert sentence_tts.default_voice("zh") == "zh-CN-YunxiNeural"
    assert sentence_tts.default_voice("ja") == ""  # no automatic reading
    anki.save_config({"tts_voices": {"zh": "fr-FR-HenriNeural"}})  # not a Mandarin voice
    assert sentence_tts.default_voice("zh") == "zh-TW-HsiaoChenNeural"
    assert client.get("/api/tts/voices?language=ja").get_json()["chosen"] == ""


def test_local_voice_preloaded_with_the_voices(client, monkeypatch):
    from miningcat.infrastructure.speech import mms_tts
    preloaded = []
    monkeypatch.setattr(mms_tts, "preload", preloaded.append)
    assert client.get("/api/tts/voices?language=nan").get_json()["chosen"] == "nan-TW-MmsTaigi"
    client.get("/api/tts/voices?language=ja")
    assert preloaded == ["nan-TW-MmsTaigi", "ja-JP-NanamiNeural"]  # preload() ignores the Edge voices


@pytest.fixture
def fake_argos(monkeypatch):
    argos = FakeArgos(installed={("zh", "en")})
    monkeypatch.setattr(translation, "argos", argos)
    return argos.downloads


def test_sentence_translation(fake_argos):
    assert translation.translate("zh", " 我们去\n公园 ") == "[zh>en] 我们去 公园"
    assert translation.translate("zh", "我們去公園") == "[zt>en] 我們去公園"  # traditional characters
    assert fake_argos == [("zt", "en")]
    anki.save_config({"translation_language": "fr"})
    assert translation.translate("ja", "公園") == "[ja>fr] 公園"
    assert fake_argos[1:] == [("ja", "en"), ("en", "fr")]  # through English
    assert translation.translate("fr", "le parc") is None  # already in French
    anki.save_config({"translation_language": ""})
    assert translation.translate("zh", "公园") is None
    with pytest.raises(translation.TranslateError):
        anki.save_config({"translation_language": "en"})
        translation.translate("yue", "公園")


def test_subtitles_translation(fake_argos):
    srt = "1\n00:00:01,000 --> 00:00:02,000\n我們去\n\n2\n00:00:03,000 --> 00:00:04,000\n<i>公園</i>\n\n3\n00:00:05,000 --> 00:00:06,000\n我們去\n"
    steps = []
    translated = translation.translate_srt("zh", srt, lambda done, total: steps.append((done, total)))
    assert translated == ("1\n00:00:01,000 --> 00:00:02,000\n[zt>en] 我們去\n\n"
                          "2\n00:00:03,000 --> 00:00:04,000\n<i>[zt>en] 公園</i>\n\n"
                          "3\n00:00:05,000 --> 00:00:06,000\n[zt>en] 我們去\n")
    assert steps == [(1, 2), (2, 2)]  # each line once
    assert fake_argos == [("zt", "en")]  # the model, downloaded once
    with pytest.raises(translation.TranslateError, match="already in English"):
        translation.translate_srt("en", "1\n00:00:01,000 --> 00:00:02,000\nHi\n")
    with pytest.raises(translation.TranslateError, match="no text"):
        translation.translate_srt("zh", "")
    anki.save_config({"translation_language": ""})
    with pytest.raises(translation.TranslateError, match="settings"):
        translation.translate_srt("zh", srt)


def test_http_translate(client, fake_argos):
    assert client.get("/api/translate/languages").get_json()["chosen"] == "en"
    res = client.post("/api/translate", json={"language": "zh", "text": "公园"}, headers=HEADERS).get_json()
    assert res == {"translation": "[zh>en] 公园", "target": "en"}
    assert client.post("/api/translate", json={"language": "yue", "text": "公園"}, headers=HEADERS).status_code == 400


@pytest.fixture
def fake_nllb(monkeypatch):
    nllb = FakeNllb(installed={"nllb-600m"})
    monkeypatch.setattr(translation, "nllb", nllb)
    return nllb


def test_translation_with_nllb(fake_argos, fake_nllb):
    anki.save_config({"translation_engine": "nllb-600m"})
    assert translation.engine() == "nllb-600m"
    assert translation.translate("zh", "我們去公園") == "{zt>en} 我們去公園"
    assert translation.translate("yue", "佢哋去飲茶") == "{yue>en} 佢哋去飲茶"  # Argos has no Cantonese
    assert translation.translate("ja", "公園", download=False) == "{ja>en} 公園"
    assert fake_argos == []  # Argos isn't used
    with pytest.raises(translation.TranslateError, match="no offline translation"):
        translation.translate("nan", "公園")
    anki.save_config({"translation_engine": "nllb-1.3b"})  # chosen, not installed
    with pytest.raises(translation.TranslateError):
        translation.translate("zh", "公園")
    fake_nllb.packages = False
    with pytest.raises(translation.TranslateError, match="make install-nllb"):
        translation.translate("zh", "公園")
    with pytest.raises(anki.AnkiError, match="Unknown translation engine"):
        anki.save_config({"translation_engine": "deepl"})


def test_subtitles_translation_with_nllb(fake_argos, fake_nllb, monkeypatch):
    monkeypatch.setattr(translation, "NLLB_LINES_PER_STEP", 2)
    anki.save_config({"translation_engine": "nllb-600m", "translation_language": "fr"})
    srt = "".join(f"{i}\n00:00:0{i},000 --> 00:00:0{i},500\n第{i}行\n\n" for i in range(1, 6))
    steps = []
    translated = translation.translate_srt("zh", srt, lambda done, total: steps.append((done, total)))
    assert "{zh>fr} 第1行" in translated and "{zh>fr} 第5行" in translated
    assert fake_nllb.batches == [2, 2, 1] and steps == [(2, 5), (4, 5), (5, 5)]


def test_translation_engines(client, fake_argos, fake_nllb, monkeypatch):
    monkeypatch.setattr(translation, "_download", translation.ModelDownload())
    monkeypatch.setattr(translation.threading, "Thread",
                        lambda target, args=(), **kw: types.SimpleNamespace(start=lambda: target(*args)))
    res = client.get("/api/translate/languages").get_json()
    assert res["engine"] == "argos" and "yue" not in [l["id"] for l in res["languages"]]
    assert [(e["id"], e["installed"]) for e in res["engines"]] == [("argos", True), ("nllb-600m", True), ("nllb-1.3b", False)]
    assert "yue" in [l["id"] for l in client.get("/api/translate/languages?engine=nllb-600m").get_json()["languages"]]
    assert client.get("/api/translate/languages?engine=deepl").status_code == 400

    # NLLB's install: its packages when they're missing, then its model
    pip = []
    def install_packages():
        pip.append(1)
        fake_nllb.packages = True
        return 0

    monkeypatch.setattr(translation.nllb_install, "install_packages", install_packages)
    fake_nllb.packages = False
    res = client.post("/api/translate/engines/nllb-1.3b/install", json={}, headers=HEADERS).get_json()
    assert res["job"]["state"] == "done" and res["job"]["engine"] == "nllb-1.3b", res
    assert pip == [1] and fake_nllb.installed("nllb-1.3b")
    assert client.post("/api/translate/engines/nllb-1.3b/install", json={}, headers=HEADERS).status_code == 400  # there
    assert client.post("/api/translate/engines/argos/install", json={}, headers=HEADERS).status_code == 400

    # with NLLB chosen, "download the models" installs its model
    anki.save_config({"translation_engine": "nllb-600m"})
    client.post("/api/translate/engines/nllb-600m/delete", json={}, headers=HEADERS)
    assert client.post("/api/translate/models", json={"language": "zh"}, headers=HEADERS).get_json()["job"]["state"] == "done"
    assert fake_nllb.installed("nllb-600m") and fake_argos == [] and pip == [1]
    res = client.post("/api/translate/engines/nllb-600m/delete", json={}, headers=HEADERS).get_json()
    assert [m["name"] for m in res["nllb"]] == ["nllb-1.3b"]
    assert client.post("/api/translate/engines/nllb-600m/delete", json={}, headers=HEADERS).status_code == 400

    # a failed install is reported
    monkeypatch.setattr(translation.nllb_install, "install_packages", lambda: 1)
    fake_nllb.packages = False
    res = client.post("/api/translate/engines/nllb-600m/install", json={}, headers=HEADERS).get_json()
    assert res["job"]["state"] == "error" and "pip" in res["job"]["error"]


def test_zhuyin_readings(client, zh_dict, fake_anki):
    lookup_entry = lambda: client.post("/api/dict/lookup", json={"language": "zh", "text": "說話"}, headers=HEADERS).get_json()["entries"][0]
    assert lookup_entry()["display_reading"] == "shuōhuà"
    assert client.post("/api/mining/reading", json={"language": "zh", "system": "zhuyin"}, headers=HEADERS).status_code == 200
    assert client.get("/api/mining/languages").get_json()["readings"] == {"zh": "zhuyin", "nan": "tailo"}
    entry = lookup_entry()
    assert entry["reading"] == "shuōhuà" and entry["display_reading"] == "ㄕㄨㄛ ㄏㄨㄚˋ"
    assert client.post("/api/mining/reading", json={"language": "ja", "system": "zhuyin"}, headers=HEADERS).status_code == 400

    # the card shows zhuyin, the word stays identified by its pinyin
    setup_chinese_notes()
    card = client.post("/api/cards", json={"language": "zh", "key_reading": "shuōhuà",
                                           "fields": {"word": "說話", "reading": "ㄕㄨㄛ ㄏㄨㄚˋ", "definition": "to talk"}},
                       headers=HEADERS).get_json()["card"]
    assert card["reading"] == "shuōhuà" and card["fields"]["reading"] == "ㄕㄨㄛ ㄏㄨㄚˋ"
    assert fake_anki.notes[card["anki_note_id"]]["fields"]["Zhuyin"] == "ㄕㄨㄛ ㄏㄨㄚˋ"
    assert words.status_of("zh", "說話", "shuōhuà")["status"] == "learning"


def test_script_settings_only_for_studied_languages(client, zh_dict):
    languages = {l["id"]: l for l in client.get("/api/mining/languages").get_json()["languages"]}
    assert languages["zh"]["studied"] and not languages["yue"]["studied"] and not languages["nan"]["studied"]


def test_translation_models(client, fake_argos, monkeypatch):
    monkeypatch.setattr(translation, "_download", translation.ModelDownload())
    monkeypatch.setattr(translation.threading, "Thread",
                        lambda target, args=(), **kw: types.SimpleNamespace(start=lambda: target(*args)))
    preferences.set_chinese_script_preference("zh", "traditional")
    res = client.post("/api/translate/models", json={"language": "zh"}, headers=HEADERS).get_json()
    assert res["job"]["state"] == "done", res
    assert fake_argos == [("zt", "en")]  # only the script the user reads
    preferences.set_chinese_script_preference("zh", "both")
    translation.start_download("ja")
    assert fake_argos[1:] == [("ja", "en")]
    assert client.post("/api/translate/models", json={"language": "en"}, headers=HEADERS).status_code == 400
    assert client.post("/api/translate/models/ko/en/delete", json={}, headers=HEADERS).status_code == 400  # not installed
    assert client.post("/api/translate/models/zt/en/delete", json={}, headers=HEADERS).status_code == 200
