import json
import zipfile

import pytest

from mining import dictionaries, lookup
from mining.languages import reading_key


def make_dictionary(path, title, terms):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": title, "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps(terms, ensure_ascii=False))
    return dictionaries.import_dictionary(path, "zh")


def term(expression, reading, glossary, tags="", sequence=0):
    return [expression, reading, tags, "", 0, glossary, sequence, ""]


def entries(text):
    return [(e["expression"], e["reading"], [(d["dictionary"], d["glossary"]) for d in e["definitions"]])
            for e in lookup.lookup("zh", text)["entries"]]


@pytest.mark.parametrize("numbered, marked", [
    ("xing2", "xíng"), ("xing2 dong4", "xíng dòng"), ("Xing2dong4", "xíngdòng"), ("lu:4", "lǜ"), ("lv4", "lǜ"),
    ("gou3", "gǒu"), ("liu2", "liú"), ("hui4", "huì"), ("ma5", "ma"), ("er2", "ér"),
])
def test_numbered_and_marked_pinyin_are_one_pronunciation(numbered, marked):
    assert reading_key(numbered, "zh") == reading_key(marked, "zh")


def test_reading_keys():
    assert reading_key("xing2", "zh") == reading_key("xíng", "zh") == reading_key("Xíng", "zh")
    assert reading_key("xing2", "zh") != reading_key("hang2", "zh")
    assert reading_key("hang4", "yue") == "hang4"  # jyutping keeps its numbers
    assert reading_key("ㄒㄧㄥˊ", "zh") == reading_key("xing2", "zh")
    assert reading_key("xíngdòng", "zh") == reading_key("xing2 dong4", "zh") == reading_key("ㄒㄧㄥˊ ㄉㄨㄥˋ", "zh")
    assert reading_key("˙ㄌㄜ", "zh") == reading_key("le5", "zh") != reading_key("le1", "zh")


def test_same_word_and_pronunciation_is_one_entry(tmp_path):
    make_dictionary(tmp_path / "a.zip", "Dict A", [
        term("行", "xíng", ["to walk", "OK"]),
        term("行", "háng", ["row"]),
        term("行動", "xíngdòng", ["action"]),
    ])
    make_dictionary(tmp_path / "b.zip", "Dict B", [term("行", "xing2", ["to walk", "to go"])])
    make_dictionary(tmp_path / "c.zip", "Dict C", [term("行", "ㄒㄧㄥˊ", ["to go", "to travel"])])
    result = entries("行")
    # 行 xíng from the three dictionaries (pinyin, numbered pinyin, zhuyin) is one entry, shown with tone marks; 行 háng is another
    assert result == [
        ("行", "xíng", [("Dict A", ["to walk", "OK"]), ("Dict B", ["to go"]), ("Dict C", ["to travel"])]),
        ("行", "háng", [("Dict A", ["row"])]),
    ]
    assert [e[:2] for e in entries("行動")] == [("行動", "xíngdòng"), ("行", "xíng"), ("行", "háng")]


def test_rows_of_one_dictionary_are_merged(tmp_path):
    make_dictionary(tmp_path / "a.zip", "Dict A", [
        term("行", "xíng", ["walk", "ok"], sequence=1),
        term("行", "xing2", ["Walk", "go"], sequence=2),  # same gloss, other case: not repeated
    ])
    assert entries("行") == [("行", "xíng", [("Dict A", ["walk", "ok", "go"])])]


def test_senses_tagged_differently_stay_apart(tmp_path):
    make_dictionary(tmp_path / "a.zip", "Dict A", [
        term("行", "xíng", ["to walk"], tags="1 v"),
        term("行", "xíng", ["capable"], tags="2 adj"),
        term("行", "xíng", ["to walk"], tags="3 v"),  # nothing new: dropped
    ])
    assert entries("行") == [("行", "xíng", [("Dict A", ["to walk"]), ("Dict A", ["capable"])])]


def test_block_texts_are_split_and_not_repeated(tmp_path):
    make_dictionary(tmp_path / "a.zip", "Dict A", [
        term("好", "hǎo", ["good"]), term("好", "hào", ["to be fond of"]),
        term("除非", "chúfēi", ["only if (..., or otherwise, ...)", "unless"]),
    ])
    make_dictionary(tmp_path / "b.zip", "Dict B", [
        term("好", "hǎo", ["1。good\n2。easy \nhào \n3。to be fond of\n4。to wish "]),
        term("除非", "chúfēi", ["1。only if\n2。unless\n3。except "]),
    ])
    make_dictionary(tmp_path / "c.zip", "Dict C", [term("好", "hào", ["【好】 [11] 1.愛。"])])

    def senses(glossary):
        return [s.get("text") or s.get("reading") for s in glossary[0]["senses"]]

    [chufei] = [e for e in lookup.lookup("zh", "除非")["entries"] if e["expression"] == "除非"]
    assert senses(chufei["definitions"][1]["glossary"]) == ["except"]
    hao3, hao4 = [e for e in lookup.lookup("zh", "好")["entries"]]
    assert senses(hao3["definitions"][1]["glossary"]) == ["easy"]
    # the senses of hào go to that entry, without the one Dict A gives
    assert [(d["dictionary"], senses(d["glossary"]) if isinstance(d["glossary"][0], dict) else d["glossary"])
            for d in hao4["definitions"]] == [("Dict A", ["to be fond of"]), ("Dict B", ["to wish"]), ("Dict C", ["愛。"])]


def test_script_g_reading_is_the_same_pronunciation():
    assert reading_key("xínɡ", "zh") == reading_key("xíng", "zh")


def test_examples_are_in_the_script_learnt(tmp_path):
    from mining import words
    words.set_chinese_script_preference("zh", "traditional")
    make_dictionary(tmp_path / "a.zip", "Dict A", [term("除非", "chúfēi", ["1。unless\n例: 除非业务好转。\nUnless business improves."])])
    [entry] = [e for e in lookup.lookup("zh", "除非")["entries"] if e["expression"] == "除非"]
    assert entry["definitions"][0]["glossary"][0]["examples"][0]["text"] == "除非業務好轉。"
