from miningcat.domain.dictionary.glossary import split_senses, structure
from miningcat.domain.dictionary.meanings import meaning_keys, new_senses


def test_plain_gloss_is_kept():
    assert split_senses("to walk", "行") is None
    assert structure(["to walk"], "行") == ["to walk"]


def test_numbered_senses_and_translated_examples():
    item = split_senses("1。only if\n2。only when \n例: 这家公司要破产了，除非业务好转。\nThe firm will go under. ", "除非")
    assert [s["text"] for s in item["senses"]] == ["only if", "only when"]
    assert item["examples"] == [{"text": "这家公司要破产了，除非业务好转。", "translation": "The firm will go under."}]


def test_header_parts_of_speech_inline_examples_and_sub_senses():
    item = split_senses("【好】 [11] 1.連詞。容易。[例]這事～辦│～看。\n2.▲〈書〉嘆詞：\n(1)表示稱賞。[例]～！", "好")
    first, second = item["senses"]
    assert first == {"text": "容易。", "tags": ["連詞"], "examples": [{"text": "這事好辦"}, {"text": "好看"}], "subs": []}
    assert second["tags"] == ["Taiwan", "書", "嘆詞"]
    assert second["subs"][0]["examples"] == [{"text": "好！"}]


def test_reading_lines_start_another_pronunciation():
    item = split_senses("1。good\nhào \n2。to be fond of ", "好")
    assert item["senses"][1] == {"reading": "hào"}


def test_meaning_keys_ignore_parentheses_and_to():
    assert meaning_keys("only if (..., or otherwise, ...)") == {"only if"}
    assert meaning_keys("to walk; to go") == {"walk", "go"}


def test_senses_already_given_are_dropped():
    seen = {"only if", "unless"}
    item = new_senses(split_senses("1。only if\n2。unless\n3。except", "除非"), seen)
    assert [s["text"] for s in item["senses"]] == ["except"]
    assert "except" in seen
    assert new_senses(split_senses("1。only if\n2。unless", "除非"), seen) is None


def test_structured_content_headword_line_is_removed():
    content = [{"tag": "div", "content": [{"tag": "div", "content": ["【", [{"tag": "span", "content": "除非"}], "】"]},
                                          {"tag": "ul", "content": [{"tag": "li", "content": "unless"}]}]}]
    [item] = structure([{"type": "structured-content", "content": content}], "除非")
    assert item["content"][0]["content"] == [{"tag": "ul", "content": [{"tag": "li", "content": "unless"}]}]
