import json
import zipfile

import pytest

from miningcat.application.mining import dictionaries, lookup, preferences, segmentation
from miningcat.application.mining.sentence_readings import annotate
from miningcat.domain.text import taiwan_readings
from miningcat.domain.text.readings import reading_key
from miningcat.domain.text.scripts import HAN_CHARACTER


def make_dictionary(path, title, terms):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": title, "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(
            [[e, r, "", "", 0, senses, 0, ""] for e, r, senses in terms], ensure_ascii=False))
    return path


# Like CC-CEDICT Zhuyin: readings of China, neutral tones.
CEDICT = [
    ("時候", "ㄕˊ˙ㄏㄡ", ["time", "length of time"]),
    ("垃圾", "ㄌㄚㄐㄧ", ["trash", "refuse", "garbage"]),
    ("喜歡", "ㄒㄧˇ˙ㄏㄨㄢ", ["to like"]),
    ("我", "ㄨㄛˇ", ["I; me"]),
    ("的", "˙ㄉㄜ", ["of"]),
    ("說話", "ㄕㄨㄛㄏㄨㄚˋ", ["to speak"]),
]
# Like 兩岸詞典: Taiwan readings, written with its "ɡ".
LIANGAN = [
    ("時候", "shíhòu", ["時間"]),
    ("星期", "xīnɡqí", ["週"]),
]


@pytest.fixture
def cedict(tmp_path):
    dictionaries.import_dictionary(make_dictionary(tmp_path / "cedict.zip", "CEDICT test", CEDICT), "zh")
    segmentation.clear_cache()
    yield
    segmentation.clear_cache()


@pytest.fixture
def both(tmp_path, cedict):
    dictionaries.import_dictionary(make_dictionary(tmp_path / "liangan.zip", "兩岸 test", LIANGAN), "zh")
    segmentation.clear_cache()


@pytest.fixture
def taiwan():
    preferences.set_taiwan_readings(True)
    yield
    preferences.set_taiwan_readings(False)


def test_every_reading_of_the_list_reads_its_word():
    readings = taiwan_readings.all_readings()
    assert readings["時候"] == "shi2 hou4"
    for word, pinyin in readings.items():
        assert pinyin, word
        assert len(pinyin.split()) == len(HAN_CHARACTER.findall(word)), word


def test_taiwan_readings_setting():
    assert not preferences.taiwan_readings()
    preferences.set_taiwan_readings(True)
    assert preferences.taiwan_readings_apply("zh") and not preferences.taiwan_readings_apply("yue")
    preferences.set_taiwan_readings(False)
    assert not preferences.taiwan_readings_apply("zh")


def readings_of(word):
    return [e["reading"] for e in lookup.lookup("zh", word)["entries"] if e["expression"] == word]


def test_without_it_the_dictionary_order_stays(both):
    assert reading_key(readings_of("時候")[0], "zh") == reading_key("shi2 hou5", "zh")
    assert not any("taiwan_reading" in e for e in lookup.lookup("zh", "時候")["entries"])


def test_taiwan_reading_comes_first(both, taiwan):
    found = readings_of("時候")
    assert reading_key(found[0], "zh") == reading_key("shi2 hou4", "zh")
    assert len(found) == 2  # the reading of China is still there
    first = lookup.lookup("zh", "時候")["entries"][0]
    assert first["taiwan_reading"] == {"replaced": ""}  # a dictionary already reads it that way


def test_taiwan_reading_replaces_the_only_one(cedict, taiwan):
    assert readings_of("時候") == ["shíhòu"]
    assert lookup.lookup("zh", "時候")["entries"][0]["taiwan_reading"] == {"replaced": "ㄕˊ˙ㄏㄡ"}
    assert "taiwan_reading" not in lookup.lookup("zh", "說話")["entries"][0]
    assert readings_of("垃圾") == ["lèsè"]  # other syllables too
    assert readings_of("說話") == ["ㄕㄨㄛㄏㄨㄚˋ"]  # not in the list


def test_sentence_readings(both, taiwan):
    tokens = {t["text"]: t["pinyin"] for t in annotate("zh", "我喜歡的時候")["tokens"]}
    assert tokens["喜歡"] == "xi3 huan1" and tokens["時候"] == "shi2 hou4"
    # the card's own reading still wins
    target = [t for t in annotate("zh", "<b>時候</b>", "shi2 hou5")["tokens"] if t["target"]]
    assert target[0]["pinyin"] == "shi2 hou5"


def test_liangan_readings_with_its_g_count(both):
    tokens = annotate("zh", "星期")["tokens"]
    assert tokens[0]["pinyin"] == "xing1 qi2"


@pytest.fixture
def client():
    pytest.importorskip("flask")
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_the_popup_gets_the_struck_reading_in_the_chosen_system(client, cedict, taiwan):
    preferences.set_reading_system("zh", "zhuyin")
    try:
        entry = client.post("/api/dict/lookup", json={"language": "zh", "text": "時候"},
                            headers={"X-MiningCat": "1"}).get_json()["entries"][0]
    finally:
        preferences.set_reading_system("zh", "pinyin")
    assert entry["display_reading"] == "ㄕˊ ㄏㄡˋ"
    assert entry["taiwan_reading"]["display_replaced"].replace(" ", "") == "ㄕˊ˙ㄏㄡ"
