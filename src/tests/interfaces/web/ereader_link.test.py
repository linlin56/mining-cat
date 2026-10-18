import json
import socket
import urllib.error
import urllib.request

import pytest

pytest.importorskip("flask")

from miningcat.application import ereader_link, study_language
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState
from miningcat.interfaces.web.lan import LAN_REQUEST

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def app():
    app = web_app.create_app(AppState())
    app.testing = True
    yield app
    app.extensions["miningcat"].lan.stop()


@pytest.fixture
def client(app):
    return app.test_client()


def lan(client, method, path, token=None, **kwargs):
    """A request of the e-reader, through its door, from another device of the network."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.open(path, method=method, headers=headers, base_url="http://192.168.1.20:5051",
                       environ_overrides={LAN_REQUEST: True}, **kwargs)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_the_access_is_off_by_default_and_its_token_is_kept():
    config = ereader_link.get_config()
    assert (config["enabled"], config["port"]) == (False, 5051)
    assert len(config["token"]) == 11 and config["token"][5] == "-"
    assert ereader_link.get_config()["token"] == config["token"]
    assert ereader_link.renew_token()["token"] != config["token"]


def test_the_port_is_checked():
    assert ereader_link.save_config({"enabled": True, "port": "6000"}) | {"token": ""} == {"enabled": True, "port": 6000, "token": ""}
    for port in (80, 70_000, "abc", True):
        with pytest.raises(ereader_link.EreaderLinkError):
            ereader_link.save_config({"port": port})
    assert ereader_link.get_config()["port"] == 6000


def test_the_e_reader_sends_a_word_with_its_token(client):
    study_language.set_current("ja")
    token = ereader_link.get_config()["token"]
    res = lan(client, "POST", "/api/inbox", token.upper(), json={"word": "猫", "sentence": "猫だ"})
    assert res.status_code == 200 and res.get_json()["item"]["word"] == "猫"
    ping = lan(client, "GET", "/api/inbox/ping", token).get_json()
    assert ping["app"] == "MiningCat" and ping["language"]["id"] == "ja"


def test_without_the_token_the_e_reader_is_refused(client):
    for token in (None, "wrong-token"):
        res = lan(client, "POST", "/api/inbox", token, json={"word": "猫", "language": "ja"})
        assert res.status_code == 401 and "token" in res.get_json()["error"]
    assert client.get("/api/inbox").get_json()["items"] == []


def test_the_door_only_opens_the_e_reader_routes(client):
    token = ereader_link.get_config()["token"]
    for method, path in [("GET", "/api/inbox"), ("GET", "/api/ereader/config"), ("POST", "/api/ereader/token"),
                         ("POST", "/api/inbox/1/delete"), ("GET", "/"), ("GET", "/settings/")]:
        assert lan(client, method, path, token).status_code == 403, path


def test_the_app_still_only_answers_on_localhost(client):
    token = ereader_link.get_config()["token"]
    res = client.post("/api/inbox", json={"word": "猫", "language": "ja"}, base_url="http://192.168.1.20:5050",
                      headers={**HEADERS, "Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_settings_open_and_close_the_door(app, client):
    port = free_port()
    config = client.post("/api/ereader/config", json={"enabled": True, "port": port}, headers=HEADERS).get_json()
    assert (config["enabled"], config["port"], config["listening"], config["error"]) == (True, port, True, None)
    assert all(a.startswith("http://") and a.endswith(f":{port}") for a in config["addresses"])
    token = config["token"]

    def send(path, data=None):
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if data else "GET",
                                         data=json.dumps(data).encode() if data else None,
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as res:
            return json.loads(res.read())

    assert send("/api/inbox", {"word": "猫", "sentence": "猫だ", "language": "ja"})["item"]["word"] == "猫"
    with pytest.raises(urllib.error.HTTPError) as refused:
        send("/api/cards")
    assert refused.value.code == 403
    refused.value.close()

    config = client.post("/api/ereader/config", json={"enabled": False}, headers=HEADERS).get_json()
    assert (config["enabled"], config["listening"]) == (False, False)
    with pytest.raises(urllib.error.URLError):
        send("/api/inbox/ping")


def test_a_port_taken_is_told(client):
    with socket.socket() as taken:
        taken.bind(("0.0.0.0", 0))
        taken.listen()
        port = taken.getsockname()[1]
        config = client.post("/api/ereader/config", json={"enabled": True, "port": port}, headers=HEADERS).get_json()
    assert config["listening"] is False and config["error"].startswith(f"Port {port} can't be opened")


def test_the_door_cant_take_the_app_s_own_port(client):
    res = client.post("/api/ereader/config", json={"enabled": True, "port": 5050}, headers=HEADERS,
                      base_url="http://127.0.0.1:5050")
    assert res.status_code == 400 and "MiningCat's own" in res.get_json()["error"]


def test_the_e_reader_looks_words_up_in_miningcat_s_dictionaries(client, tmp_path):
    import zipfile
    from miningcat.application.mining import dictionaries, words
    path = tmp_path / "ja.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps({"title": "Test JMdict", "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps([["食べる", "たべる", "v1", "v1", 100, ["to eat"], 1, ""]], ensure_ascii=False))
    dictionaries.import_dictionary(path)
    token = ereader_link.get_config()["token"]

    def look_up():
        res = lan(client, "POST", "/api/inbox/lookup", token, json={"word": "食べ", "after": "た。次の文。", "language": "ja"})
        assert res.status_code == 200
        return res.get_json()["entries"][0]

    entry = look_up()
    assert (entry["expression"], entry["status"]["status"], entry["in_inbox"]) == ("食べる", "new", False)
    assert entry["definitions"] == [{"dictionary": "Test JMdict", "html": "<div>to eat</div>"}]
    words.set_status("ja", "食べる", "たべる", "known")
    lan(client, "POST", "/api/inbox", token, json={"word": "食べた", "sentence": "食べた。", "language": "ja"})
    entry = look_up()
    assert (entry["status"]["status"], entry["in_inbox"]) == ("known", True)
