import pytest

pytest.importorskip("flask")
pytest.importorskip("opencc")

from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def client():
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def convert(client, text, target, language="zh"):
    return client.post("/api/chinese/convert", json={"text": text, "target": target, "language": language}, headers=HEADERS)


def test_converts_to_traditional_with_taiwan_forms_and_quotes(client):
    res = convert(client, "“我们说台湾话。”", "traditional")
    assert res.status_code == 200
    assert res.get_json() == {"text": "「我們說臺灣話。」", "script": "traditional", "source": "simplified"}


def test_converts_to_simplified(client):
    assert convert(client, "「我們說話。」", "simplified").get_json() == {
        "text": "“我们说话。”", "script": "simplified", "source": "traditional"}


def test_leaves_a_text_already_in_the_script_as_it_is(client):
    # OpenCC alone would write 臺北 and 裡面
    assert convert(client, "我住在台北，裡面", "traditional").get_json()["text"] == "我住在台北，裡面"
    assert convert(client, "台北里面", "simplified").get_json()["text"] == "台北里面"


def test_converts_only_the_lines_not_in_the_script(client):
    text = "我住在台北里面。\n我们说话。\n"
    assert convert(client, text, "traditional").get_json()["text"] == "我住在台北里面。\n我們說話。\n"


def test_cantonese_takes_hong_kong_forms(client):
    assert convert(client, "里面说", "traditional", "yue").get_json()["text"] == "裏面説"  # Hong Kong forms


def test_converts_the_quotation_marks_of_every_line(client):
    assert convert(client, "“你好。”\n“我们”\n", "traditional").get_json()["text"] == "「你好。」\n「我們」\n"
    assert convert(client, "「你好」", "simplified").get_json()["text"] == "“你好”"


def test_cantonese_simplifies_hong_kong_forms(client):
    assert convert(client, "衞生，裏面説", "simplified", "yue").get_json()["text"] == "卫生，里面说"


def test_tells_the_script_of_most_characters_without_conversion(client):
    assert convert(client, "我們說话", "none").get_json() == {"text": "我們說话", "script": "traditional", "source": "traditional"}
    assert convert(client, "你好", "none").get_json()["script"] == "both"
    # a tie: the study's default tag
    assert convert(client, "我們说", "none").get_json()["script"] == "both"


def test_tells_the_script_of_a_long_text_from_all_over_it(client):
    assert convert(client, "說" * 30_000 + "说" * 200_000, "none").get_json()["script"] == "simplified"


def test_reads_a_long_text_without_conversion(client):
    assert convert(client, "说" * 250_000, "none").status_code == 200
    assert convert(client, "说" * 250_000, "traditional").status_code == 400


def test_refuses_an_unknown_script(client):
    assert convert(client, "我们", "klingon").status_code == 400


@pytest.mark.parametrize("language", ["ja", "nan"])
def test_refuses_a_language_not_converted(client, language):
    assert convert(client, "学校", "traditional", language).status_code == 400
