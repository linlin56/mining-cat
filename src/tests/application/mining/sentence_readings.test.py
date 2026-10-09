import json
import zipfile

import pytest

from miningcat.application import anki
from miningcat.application.mining import dictionaries, segmentation
from miningcat.application.mining.sentence_readings import annotate
from miningcat.domain.sentence_readings.card_sentence import word_field
from miningcat.domain.text.zhuyin import numbered_pinyin


def cedict_entry(senses):
    """A glossary like the CC-CEDICT Yomitan dictionaries': a headword div, then the senses as list items."""
    return [{"type": "structured-content", "content": [{"tag": "div", "content": [
        {"tag": "div", "data": {"cccedict": "headword"}, "content": ["【x】"]},
        {"tag": "ul", "data": {"cccedict": "definition"}, "content": [{"tag": "li", "content": s} for s in senses]},
    ]}]}]


# Readings in zhuyin, as in the CC-CEDICT Zhuyin dictionary; the senses decide when nothing else does.
TERMS = [
    ("繁體字", "ㄈㄢˊㄊㄧˇㄗˋ", ["traditional Chinese character"]),
    ("你", "ㄋㄧˇ", ["you"]),
    ("我", "ㄨㄛˇ", ["I; me"]),
    ("他", "ㄊㄚ", ["he; him"]),
    ("都", "ㄉㄨ", ["surname Du"]),
    ("都", "ㄉㄡ", ["all; both", "(used for emphasis) even", "already"]),
    ("都", "ㄉㄨ", ["capital city", "metropolis"]),
    ("看", "ㄎㄢ", ["to look after", "to take care of", "to watch", "to guard"]),
    ("看", "ㄎㄢˋ", ["to see", "to read", "to watch", "to consider", "to visit"]),
    ("得", "ㄉㄜˊ", ["to obtain", "to get", "to gain", "to catch", "to be finished"]),
    ("得", "ㄉㄜˋ", ["used in 得瑟"]),
    ("得", "˙ㄉㄜ", ["structural particle"]),
    ("得", "ㄉㄟˇ", ["to have to", "must", "ought to", "to need to"]),
    ("懂", "ㄉㄨㄥˇ", ["to understand"]),
    ("嗎", "ㄇㄚˊ", ["used in 嗎啡"]),
    ("嗎", "ㄇㄚˇ", ["used in 嗎啡"]),
    ("嗎", "˙ㄇㄚ", ["(question particle)"]),
    ("走", "ㄗㄡˇ", ["to walk"]),
    ("跑", "ㄆㄠˇ", ["to run"]),
    ("很", "ㄏㄣˇ", ["very"]),
    ("快", "ㄎㄨㄞˋ", ["fast"]),
    ("了", "˙ㄌㄜ", ["(completed action marker)"]),
    ("了", "ㄌㄧㄠˇ", ["to finish", "to understand"]),
    ("長", "ㄔㄤˊ", ["long", "length"]),
    ("長", "ㄓㄤˇ", ["chief", "to grow", "to develop"]),
    ("高", "ㄍㄠ", ["tall; high"]),
    ("還", "ㄏㄞˊ", ["still", "yet", "also"]),
    ("還", "ㄏㄨㄢˊ", ["to pay back", "to return"]),
    ("錢", "ㄑㄧㄢˊ", ["money"]),
    ("好", "ㄏㄠˇ", ["good", "well"]),
    ("好", "ㄏㄠˋ", ["to be fond of"]),
    ("著", "˙ㄓㄜ", ["aspect particle"]),
    ("著", "ㄓㄠˊ", ["to touch", "to feel"]),
    ("著", "ㄓㄨˋ", ["to make known", "to write"]),
    ("找", "ㄓㄠˇ", ["to look for"]),
    ("數", "ㄕㄨˇ", ["to count"]),
    ("數", "ㄕㄨˋ", ["number", "figure"]),
    ("一", "ㄧ", ["one"]),
    ("受", "ㄕㄡˋ", ["to receive"]),
    ("不", "ㄅㄨˋ", ["not"]),
]


@pytest.fixture
def cedict(tmp_path):
    path = tmp_path / "cedict.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "CC-CEDICT test", "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(
            [[e, r, "", "", 0, cedict_entry(s), 0, ""] for e, r, s in TERMS], ensure_ascii=False))
    dictionaries.import_dictionary(path, "zh")
    segmentation.clear_cache()
    yield
    segmentation.clear_cache()


@pytest.mark.parametrize("reading, numbered", [
    ("ㄈㄢˊㄊㄧˇㄗˋ", "fan2 ti3 zi4"), ("˙ㄇㄚ", "ma5"), ("ㄍㄠ", "gao1"), ("fántǐzì", "fan2 ti3 zi4"),
    ("fan2 ti3 zi4", "fan2 ti3 zi4"), ("lǜ", "lü4"), ("ㄓㄜˋㄦ", "zher4"), ("not a reading", ""),
])
def test_numbered_pinyin(reading, numbered):
    assert numbered_pinyin(reading) == numbered


def test_sentence_with_one_bracketed_reading_per_word(cedict):
    result = annotate("zh", "<b>繁體字</b>你都看得懂嗎？", "ㄈㄢˊㄊㄧˇㄗˋ")
    assert result["field"] == "<b>繁體字[fan2 ti3 zi4]</b>你[ni3]都[dou1]看[kan4]得[de5]懂[dong3]嗎[ma5]？"
    tokens = {t["text"]: t for t in result["tokens"]}
    assert tokens["繁體字"]["target"] and not tokens["你"]["target"]
    # the other readings stay available to correct a choice
    assert [c["pinyin"] for c in tokens["得"]["choices"]] == ["de2", "de4", "de5", "dei3"]


@pytest.mark.parametrize("sentence, field", [
    ("我得走了。", "我[wo3]得[dei3]走[zou3]了[le5]。"),          # must
    ("他跑得很快。", "他[ta1]跑[pao3]得[de5]很[hen3]快[kuai4]。"),  # complement
    ("他得了。", "他[ta1]得[de2]了[le5]。"),                       # obtained
    ("我受不了了", "我[wo3]受[shou4]不[bu4]了[liao3]了[le5]"),
    ("他長得很高。", "他[ta1]長[zhang3]得[de5]很[hen3]高[gao1]。"),
    ("很長", "很[hen3]長[chang2]"),
    ("他還錢了。", "他[ta1]還[huan2]錢[qian2]了[le5]。"),
    ("他還好嗎？", "他[ta1]還[hai2]好[hao3]嗎[ma5]？"),
    ("他看著我。", "他[ta1]看[kan4]著[zhe5]我[wo3]。"),
    ("找著了", "找[zhao3]著[zhao2]了[le5]"),
    ("我數一數。", "我[wo3]數[shu3]一[yi1]數[shu3]。"),
])
def test_context_chooses_the_reading(cedict, sentence, field):
    assert annotate("zh", sentence)["field"] == field


def test_words_missing_from_the_dictionaries_and_punctuation_are_kept(cedict):
    assert annotate("zh", "Hello，你 & 他<br>好")["field"] == "Hello，你[ni3] &amp; 他[ta1]<br>好[hao3]"


def test_the_cards_word_keeps_the_reading_picked_in_the_popup(cedict):
    assert annotate("zh", "你<b>還</b>錢", "ㄏㄞˊ")["field"] == "你[ni3]<b>還[hai2]</b>錢[qian2]"


def test_card_fields_are_derived_when_the_creator_gave_none(cedict):
    fields = anki.derived_fields("zh", {"word": "看", "reading": "kàn", "sentence": "你<b>看</b>"})
    assert fields["word_readings"] == "看[kan4]"
    assert fields["sentence_readings"] == "你[ni3]<b>看[kan4]</b>"
    given = anki.derived_fields("zh", {"word": "看", "reading": "kàn", "sentence": "你<b>看</b>", "sentence_readings": "x"})
    assert "sentence_readings" not in given


def test_word_field():
    assert word_field("繁體字", "ㄈㄢˊㄊㄧˇㄗˋ") == "繁體字[fan2 ti3 zi4]"
    assert word_field("繁體字", "") == "繁體字"


def test_other_languages_get_nothing(cedict):
    assert annotate("ja", "<b>猫</b>だ")["field"] == ""
