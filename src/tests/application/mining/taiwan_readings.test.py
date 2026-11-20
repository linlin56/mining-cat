import json
import zipfile

import pytest

from miningcat.application.mining import dictionaries, lookup, preferences, segmentation, words
from miningcat.application.mining.sentence_readings import annotate
from miningcat.domain.text import taiwan_readings
from miningcat.domain.text.readings import reading_key
from miningcat.domain.sentence_readings.card_sentence import display_pinyin
from miningcat.domain.text.scripts import HAN_CHARACTER
from zhuyin_converter import pinyin_to_zhuyin


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
    # 和 without the Taiwan han4: its first entry is its main reading
    ("和", "ㄏㄜˊ", ["and", "together with", "with", "harmonious"]),
    ("和", "ㄏㄨㄛˋ", ["to mix together"]),
    ("和", "ㄏㄜˋ", ["to compose a poem in reply"]),
    # a simplified dictionary entry
    ("时候", "ㄕˊ˙ㄏㄡ", ["time (simplified)"]),
]
# Like 兩岸詞典: Taiwan readings, written with its "ɡ".
LIANGAN = [
    ("時候", "shíhòu", ["時間"]),
    ("星期", "xīnɡqí", ["週"]),
    ("垃圾", "lèsè", ["廢棄物"]),
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


def listed(word):
    """The reading taiwan_readings.toml gives a word these tests use (時候, 垃圾, 喜歡)."""
    reading = taiwan_readings.taiwan_reading(word)
    assert reading, f"the tests need {word} in taiwan_readings.toml"
    return reading


def accented(word):
    return display_pinyin(listed(word), "pinyin").replace(" ", "")


def test_every_reading_of_the_list_reads_its_word():
    readings = taiwan_readings.all_readings()  # parse() refuses a word listed twice or an unreadable reading
    assert len(readings) > 100
    for word, pinyin in readings.items():
        assert len(pinyin.split()) == len(HAN_CHARACTER.findall(word)), word


def test_the_list_format():
    assert taiwan_readings.parse('["days"]\n"星期一" = "xing1 qi2 yi1"  # a comment\n') == {"星期一": "xing1 qi2 yi1"}
    assert taiwan_readings.parse('["a"]\n"時候" = "shíhòu"') == {"時候": "shi2 hou4"}  # tone marks work too
    for wrong in ('["a"]\n"時候" = "shi2 hou4"\n["b"]\n"時候" = "shi2 hou4"',  # listed twice
                  '["a"]\n"時候" = "not a reading"',
                  '"時候" = "shi2 hou4"'):  # outside a section
        with pytest.raises(ValueError):
            taiwan_readings.parse(wrong)


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
    assert reading_key(found[0], "zh") == reading_key(listed("時候"), "zh")
    assert len(found) == 2  # the reading of China is still there
    first = lookup.lookup("zh", "時候")["entries"][0]
    assert first["taiwan_reading"] == {"replaced": ""}  # a dictionary already reads it that way


def test_taiwan_reading_replaces_the_only_one(cedict, taiwan):
    assert readings_of("時候") == [accented("時候")]
    assert lookup.lookup("zh", "時候")["entries"][0]["taiwan_reading"] == {"replaced": "ㄕˊ˙ㄏㄡ"}
    assert "taiwan_reading" not in lookup.lookup("zh", "說話")["entries"][0]
    assert readings_of("垃圾") == [accented("垃圾")]  # other syllables too
    assert readings_of("說話") == ["ㄕㄨㄛㄏㄨㄚˋ"]  # not in the list


def test_sentence_readings(both, taiwan):
    tokens = {t["text"]: t["pinyin"] for t in annotate("zh", "我喜歡說話的時候")["tokens"]}
    assert tokens["喜歡"] == listed("喜歡") and tokens["時候"] == listed("時候")  # in the list
    assert tokens["說話"] == "shuo1 hua4"  # not in it: the dictionary's reading
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
    assert entry["display_reading"] == pinyin_to_zhuyin(listed("時候"))
    assert entry["taiwan_reading"]["display_replaced"].replace(" ", "") == "ㄕˊ˙ㄏㄡ"


def test_the_taiwan_reading_goes_to_the_main_entry(cedict, taiwan):
    entries = [e for e in lookup.lookup("zh", "和")["entries"] if e["expression"] == "和"]
    forced = [e for e in entries if "taiwan_reading" in e]
    assert len(forced) == 1 and forced[0]["taiwan_reading"]["replaced"] == "ㄏㄜˊ"  # "and", not "to mix"
    assert reading_key(forced[0]["reading"], "zh") == reading_key(listed("和"), "zh")


def test_a_simplified_word_gets_the_reading_of_its_traditional_form(cedict, taiwan):
    entry = lookup.lookup("zh", "时候")["entries"][0]
    assert entry["expression"] == "时候" and reading_key(entry["reading"], "zh") == reading_key(listed("時候"), "zh")


def test_a_word_saved_under_the_dictionary_reading_keeps_its_status(cedict, taiwan):
    words.set_status("zh", "時候", "ㄕˊ˙ㄏㄡ", "learning")
    entry = lookup.lookup("zh", "時候")["entries"][0]
    assert entry["status"]["status"] == "learning"
    assert entry["status_reading"] == "ㄕˊ˙ㄏㄡ"  # where the popup saves a new status


def test_frequencies_follow_the_dictionary_reading(tmp_path, cedict, taiwan):
    path = tmp_path / "freq.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Freq test", "revision": "1", "format": 3}))
        z.writestr("term_meta_bank_1.json", json.dumps(
            [["時候", "freq", {"reading": "shi2 hou5", "frequency": 41}]], ensure_ascii=False))
    dictionaries.import_dictionary(path, "zh")
    entry = lookup.lookup("zh", "時候")["entries"][0]
    assert [f["value"] for f in entry["frequencies"]] == [41]


def test_a_word_saved_under_another_entry_keeps_its_status(both, taiwan):
    words.set_status("zh", "垃圾", "ㄌㄚㄐㄧ", "known")  # saved under CC-CEDICT's lājī; 兩岸 reads it lèsè
    entry = lookup.lookup("zh", "垃圾")["entries"][0]
    assert reading_key(entry["reading"], "zh") == reading_key(listed("垃圾"), "zh")
    assert entry["status"]["status"] == "known" and entry["status_reading"] == "ㄌㄚㄐㄧ"


def test_turned_off_a_word_saved_under_the_taiwan_reading_keeps_its_status(cedict):
    words.set_status("zh", "時候", accented("時候"), "learning")  # saved while it was on
    entry = lookup.lookup("zh", "時候")["entries"][0]
    assert entry["reading"] == "ㄕˊ˙ㄏㄡ" and entry["status"]["status"] == "learning"
    assert entry["status_reading"] == accented("時候") and "_taiwan_alias" not in entry
