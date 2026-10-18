from miningcat.domain.dictionary.glossary_html import glossary_html


def test_plain_glosses_are_a_list():
    assert glossary_html(["to speak", "to <say>"]) == "<ul><li>to speak</li><li>to &lt;say&gt;</li></ul>"
    assert glossary_html(["to speak"]) == "<div>to speak</div>"


def test_structured_content_keeps_its_layout_without_images_links_or_styles():
    content = {"tag": "div", "lang": "zh", "style": {"color": "red"}, "content": [
        {"tag": "a", "href": "?query=說", "content": "說"},
        {"tag": "img", "path": "a.png"},
        {"tag": "ul", "content": [{"tag": "li", "content": "to speak"}, {"tag": "li", "content": ["to", {"tag": "br"}, "say"]}]},
        {"tag": "details", "content": [{"tag": "summary", "content": "more"}, {"tag": "td", "colSpan": 2, "content": 1}]},
    ]}
    assert glossary_html([{"type": "structured-content", "content": content}]) == (
        '<div><div lang="zh"><span>說</span><ul><li>to speak</li><li>to<br>say</li></ul>'
        '<div><div>more</div><td colspan="2">1</td></div></div></div>')


def test_senses_are_numbered_with_their_tags_examples_and_readings():
    senses = {"type": "senses", "examples": [{"text": "美好", "translation": "beautiful"}], "senses": [
        {"reading": "shuō"},
        {"text": "用言語表達意思。", "tags": ["動詞"], "examples": [{"text": "我在說話"}], "subs": []},
        {"text": "閒聊。", "tags": [], "examples": [], "subs": [{"text": "閒談。", "tags": [], "examples": [], "subs": []}]},
        {"reading": "shuì"},
        {"text": "勸說。", "tags": [], "examples": [], "subs": []},
    ]}
    assert glossary_html([senses]) == (
        "<div><p><b>shuō</b></p><ol><li><b>動詞</b> 用言語表達意思。<ul><li><i>我在說話</i></li></ul></li>"
        "<li>閒聊。<ol><li>閒談。</li></ol></li></ol><p><b>shuì</b></p><div>勸說。</div>"
        "<ul><li><i>美好</i><br>beautiful</li></ul></div>")
