import importlib.util
import json
import sys
import zipfile

import pytest

from mining import anki, dictionaries, languages, lookup, segment, taigi, words

HEADERS = {"X-MiningCat": "1"}
needs_taibun = pytest.mark.skipif(importlib.util.find_spec("taibun") is None, reason="taibun isn't installed")


# ---------------------------------------------------------------- romanizations

@pytest.mark.parametrize("text, tailo, poj, numbers", [
    ("tsia̍h-pn̄g", "tsia̍h-pn̄g", "chia̍h-pn̄g", "tsiah8-png7"),
    ("chia̍h-pn̄g", "tsia̍h-pn̄g", "chia̍h-pn̄g", "tsiah8-png7"),
    ("tsiah8-png7", "tsia̍h-pn̄g", "chia̍h-pn̄g", "tsiah8-png7"),
    ("Tâi-oân", "Tâi-uân", "Tâi-oân", "Tai5-uan5"),
    ("o͘-á", "oo-á", "o͘-á", "oo1-a2"),
    ("hó͘", "hóo", "hó͘", "hoo2"),
    ("chheⁿ", "tshenn", "chheⁿ", "tshenn1"),
    ("Siáⁿ-mih", "Siánn-mih", "Siáⁿ-mih", "Siann2-mih4"),
    ("khòaⁿ", "khuànn", "khoàⁿ", "khuann3"),  # the mark goes on the a before a nasal (modern POJ)
    ("kué-tsí", "kué-tsí", "kóe-chí", "kue2-tsi2"),
    ("hoe", "hue", "hoe", "hue1"),
    ("ūi", "uī", "ūi", "ui7"),
    ("chiū", "tsiū", "chiū", "tsiu7"),
    ("eng", "ing", "eng", "ing1"),
    ("se̍k", "si̍k", "se̍k", "sik8"),
    ("nn̄g", "nn̄g", "nn̄g", "nng7"),
    ("hm̄", "hm̄", "hm̄", "hm7"),
    ("Pháinn-sè--lah", "Pháinn-sè--lah", "Pháiⁿ-sè--lah", "Phainn2-se3--lah4"),
    ("sìⁿh", "sìnnh", "sìhⁿ", "sinnh3"),
    ("OK", "OK", "OK", "OK4"),
])
def test_romanizations(text, tailo, poj, numbers):
    assert taigi.respell(text, "tailo") == tailo
    assert taigi.respell(text, "poj") == poj
    assert taigi.respell(text, "tailo", numbers=True) == numbers


def test_words_that_arent_taigi_stay_as_they_are():
    assert taigi.respell("check the Facebook 2024 covid19", "tailo") == "check the Facebook 2024 covid19"
    assert taigi.parse_syllable("xyz") is None
    assert taigi.parse_syllable("tsá̍h") is None      # two tone marks
    assert taigi.parse_syllable("tsiah4") is not None
    assert taigi.parse_syllable("tsia̍h4") is None     # the mark and the number disagree
    assert taigi.parse_word("tsiah-xyz") is None


def test_neutral_tone_and_capitals():
    syllables = taigi.parse_word("Tsáu--ah")
    assert [s.neutral for s in syllables] == [False, True]
    assert syllables[0].capital and not syllables[1].capital
    assert taigi.write_word(syllables, "poj") == "Cháu--ah"


def test_reading_key_is_the_same_whatever_the_spelling():
    assert taigi.reading_key("Tâi-oân") == taigi.reading_key("tai5-uan5") == taigi.reading_key("Tâi-uân") == "tai5uan5"
    assert taigi.reading_key("hello world") == ""


@pytest.mark.parametrize("text, system", [
    ("我欲食飯", "hanji"), ("Guá beh tsia̍h-pn̄g", "tailo"), ("Góa beh chia̍h-pn̄g", "poj"),
    ("chhiⁿ o͘", "poj"), ("123", ""),
])
def test_detect(text, system):
    assert taigi.detect(text) == system


def test_convert_refuses_an_unknown_system():
    with pytest.raises(ValueError):
        taigi.convert("guá", "klingon")
    assert taigi.convert("", "poj") == ""


def test_alignment_letters_of_romanized_text():
    assert taigi.alignment_letters("Góa beh chia̍h-pn̄g, chhiⁿ!") == "gua beh tsiah png tshinn"


# ---------------------------------------------------------------- Hanji (taibun)

@needs_taibun
def test_hanji_to_romanizations():
    assert taigi.convert("我欲去臺北食飯。", "tailo") == "Guá beh khì Tâi-pak tsia̍h-pn̄g."
    assert taigi.convert("我欲去臺北食飯。", "poj") == "Góa beh khì Tâi-pak chia̍h-pn̄g."
    assert taigi.convert("我欲去臺北食飯。", "tailo", numbers=True) == "Gua2 beh4 khi3 Tai5-pak4 tsiah8-png7."
    assert taigi.romanize("食飯。") == "tsia̍h-pn̄g。"  # the original's punctuation
    assert taigi.reading("食飯", "poj") == "chia̍h-pn̄g"
    assert taigi.reading("abc") == ""


@needs_taibun
def test_subtitles_keep_their_index_and_timecodes(tmp_path):
    import chinese_converter

    srt = tmp_path / "a.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,639\n我欲去臺北食飯。\n\n2\n00:00:01,720 --> 00:00:03,751\n今仔日\n天氣真好。\n", encoding="utf-8")
    chinese_converter.convert_srt_file(srt, "nan", "poj")
    assert srt.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,639\nGóa beh khì Tâi-pak chia̍h-pn̄g.\n\n"
        "2\n00:00:01,720 --> 00:00:03,751\nKin-á-ji̍t\nThiⁿ-khì chin-hó.\n"
    )
    assert taigi.convert("我\n你", "tailo") == "Guá\nLí"


@needs_taibun
def test_romanized_text_to_hanji():
    assert taigi.convert("Guá beh khì Tâi-pak tsia̍h-pn̄g.", "hanji") == "我欲去台北食飯。"
    assert taigi.convert("Góa ài lí", "hanji") == "我愛你"
    assert taigi.convert("Lí tsia̍h-pá--buē?", "hanji") == "你食飽未？"
    # a word in capitals isn't Taigi, a syllable without Hanji stays romanized (Hàn-lô)
    assert taigi.convert("OK, guá", "hanji") == "OK, 我"


def test_syllables_without_hanji_stay_romanized():
    index = {("gua2",): "我", ("ah4",): "啊"}
    pieces = taigi._word_to_hanji(taigi.parse_word("guá-tsoo--ah"), index, 1)
    # a neutral tone takes the Hanji of any tone of the syllable
    assert pieces == [("我", True), ("tsoo", False), ("啊", True)]


@needs_taibun
def test_annotate_and_tokenize():
    assert taigi.annotate("我 beh 去臺北。") == [
        ("我", "guá"), (" ", ""), ("beh", ""), (" ", ""), ("去", "khì"), ("臺北", "Tâi-pak"), ("。", ""),
    ]
    assert taigi.tokenize("我欲去臺北食飯。Guá beh tsia̍h-pn̄g, OK") == [
        "我", "欲", "去", "臺北", "食飯", "Guá", "beh", "tsia̍h-pn̄g", "OK",
    ]
    assert taigi.tts_text("我欲食飯") == "góa beh chia̍h-pn̄g"
    assert taigi.alignment_letters("「你好！」伊講。") == "li ho i kong"


@pytest.fixture
def no_taibun(monkeypatch):
    monkeypatch.setitem(sys.modules, "taibun", None)
    taigi._converter.cache_clear()
    taigi._hanji_index.cache_clear()
    yield
    taigi._converter.cache_clear()
    taigi._hanji_index.cache_clear()


def test_without_taibun(no_taibun):
    with pytest.raises(RuntimeError, match="taibun"):
        taigi.convert("我", "tailo")
    with pytest.raises(RuntimeError, match="taibun"):
        taigi.convert("guá", "hanji")
    assert taigi.reading("我") == ""
    assert taigi.annotate("我") == [("我", "")]
    assert taigi.tokenize("我欲 guá") == ["我", "欲", "guá"]


# ---------------------------------------------------------------- dictionaries, words, cards

def test_text_variants_and_readings():
    assert languages.text_variants("Chia̍h-pn̄g", "nan") == ["Chia̍h-pn̄g", "chia̍h-pn̄g", "tsia̍h-pn̄g", "tsiah8-png7"]
    assert languages.text_variants("食飯", "nan") == ["食飯"]
    assert languages.normalize_reading("Chia̍h-pn̄g", "nan") == languages.normalize_reading("tsia̍h-pn̄g", "nan") == "tsia̍hpn̄g"
    assert languages.reading_key("chia̍h-pn̄g", "nan") == languages.reading_key("tsiah8 png7", "nan")
    assert languages.reading_match("tsiah8-png7", "tsia̍h-pn̄g", "nan") == 2
    assert languages.reading_match("tsiah4-png7", "tsia̍h-pn̄g", "nan") == 1
    assert languages.reading_match("guá", "tsia̍h-pn̄g", "nan") == 0


def test_taigi_dictionaries_are_recognized():
    samples = [("食飯", "tsia̍h-pn̄g"), ("台灣", "Tâi-uân"), ("歹勢", "pháinn-sè"), ("媠", "suí"), ("有", "ū")]
    assert languages.guess_dictionary_language(samples) == "nan"
    assert languages.guess_dictionary_language([("吃饭", "chī fàn"), ("台湾", "tái wān"), ("好", "hǎo")]) == "zh"


def test_reading_system_setting():
    assert words.reading_system("nan") == "tailo"
    assert words.display_reading("nan", "食飯", "chia̍h-pn̄g") == "tsia̍h-pn̄g"
    words.set_reading_system("nan", "poj")
    assert words.reading_system("nan") == "poj"
    assert words.display_reading("nan", "食飯", "tsia̍h-pn̄g") == "chia̍h-pn̄g"
    with pytest.raises(words.WordError):
        words.set_reading_system("nan", "pinyin")
    with pytest.raises(words.WordError):
        words.set_reading_system("fr", "poj")
    assert words.reading_system("fr") == ""


def test_a_word_saved_in_poj_is_the_tailo_word():
    words.set_status("nan", "食飯", "chia̍h-pn̄g", "learning")
    assert words.status_of("nan", "食飯", "tsia̍h-pn̄g")["status"] == "learning"


def test_card_fields():
    fields = anki.derived_fields("nan", {"word": "食飯", "reading": "tsia̍h-pn̄g", "sentence": "<b>食飯</b>"})
    assert fields["tailo"] == "tsia̍h-pn̄g" and fields["poj"] == "chia̍h-pn̄g"
    assert fields["word_readings"] == "食飯[tsia̍h-pn̄g]"
    assert fields["sentence_readings"].startswith("<b>")
    kept = {"word": "x", "reading": "", "tailo": "kept", "poj": "kept", "word_readings": "kept", "sentence_readings": "kept"}
    assert anki.derived_fields("nan", kept) == {}
    assert anki.derived_fields("fr", {"word": "chat"}) == {}


@needs_taibun
def test_card_fields_from_hanji_only():
    fields = anki.derived_fields("nan", {"word": "食飯", "reading": "", "sentence": "我欲<b>食飯</b>。"})
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
    segment.clear_cache()
    info = dictionaries.import_dictionary(make_dictionary(tmp_path / "nan.zip", NAN_TERMS))
    yield info
    segment.clear_cache()


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
    result = segment.colour("nan", text)
    assert [w["headword"] for w in result["words"]] == ["我", "欲", "食飯"]
    assert {w["headword"]: w["status"] for w in result["words"]}["食飯"] == "known"
    assert [text[s:s + n] for s, n, _ in result["tokens"]] == ["Góa", "beh", "chia̍h-pn̄g", "我", "欲", "食飯", "xyz"]


# ---------------------------------------------------------------- web

@pytest.fixture
def client():
    pytest.importorskip("flask")
    from web import app as web_app
    from web.state import AppState
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


# ---------------------------------------------------------------- OCR

@pytest.mark.parametrize("ocr, repaired", [
    ("Liân siã-thuân mã bồ tsham-ka", "Liân siā-thuân mā bô tsham-ka"),     # ã -> ā, ồ -> ô
    ("Siunn-beh bih-sio-tshue ê lâng lãi tsia tsip-hàp", "Siunn-beh bih-sio-tshue ê lâng lāi tsia tsip-ha̍p"),
    ("Lóng-sĩ tshù lí ê sìn-sít", "Lóng-sī tshù lí ê sìn-si̍t"),             # any mark on -t: the 8th tone
    ("Put-chai-put-kak chiân-chò kơ tan-it", "Put-chai-put-kak chiân-chò ko͘ tan-it"),  # POJ's o͘
    ("Huan-l6 kau bue", "Huan-lo kau bue"),                                  # digits read for letters
    ("Li u leh khuann-b6", "Li u leh khuann-bo"),
    ("|ai 1ang", "lai lang"),
    ('chiâ"-chò Siu -beh', "chiâⁿ-chò Siuⁿ-beh"),                             # POJ's ⁿ read as a quote or a space
    ('tsit jī "ah" tsiânn - hó', 'tsit jī "ah" tsiânn - hó'),               # but quotes and dashes stay
    ("tsiah8-png7 ho2", "tsiah8-png7 ho2"),                                  # tone numbers stay
    ("gi-ta（吉他）", "gi-ta（吉他）"),
])
def test_repair_ocr(ocr, repaired):
    assert taigi.repair_ocr(ocr) == repaired
