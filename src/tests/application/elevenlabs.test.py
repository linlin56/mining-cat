import io
import os
import json
import urllib.error

import numpy as np
import pytest

from miningcat.application import anki, elevenlabs
from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.options import language_options
from miningcat.application.converter.steps import speech_synthesis
from miningcat.application.mining import sentence_tts
from miningcat.domain.languages import Language
from miningcat.infrastructure.speech import elevenlabs_tts
from miningcat.infrastructure.speech.elevenlabs_tts import ElevenLabs, ElevenLabsError

HEADERS = {"X-MiningCat": "1"}
VIVIAN = "xrDmUzhnE51Df8z38r1M"


def _refusal(code: int, status: str, message: str = "") -> urllib.error.HTTPError:
    body = json.dumps({"detail": {"status": status, "message": message}}).encode()
    return urllib.error.HTTPError("https://api.elevenlabs.io", code, "refused", {}, io.BytesIO(body))


@pytest.fixture
def api(monkeypatch):
    """ElevenLabs' API, faked: the requests sent, and the answers given by path (an exception is raised)."""
    sent, answers = [], {}

    def send(request):
        path = request.full_url.removeprefix(elevenlabs_tts.API).split("?")[0]
        sent.append({"path": path, "url": request.full_url, "key": request.get_header("Xi-api-key"),
                     "body": json.loads(request.data) if request.data else None})
        answer = answers.get(path, b"mp3")
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(elevenlabs_tts, "_send", send)
    monkeypatch.setattr(elevenlabs, "_latest", {})
    monkeypatch.setattr(elevenlabs_tts.time, "sleep", lambda s: None)
    return type("Api", (), {"sent": sent, "answers": answers})


@pytest.fixture
def set_up(api):
    """ElevenLabs set up for Mandarin, not the main voice; edge-tts used (the default)."""
    anki.save_config({"tts_use_edge": True})
    api.answers[f"/v1/voices/{VIVIAN}"] = json.dumps({"name": "Vivian"}).encode()
    elevenlabs.save_settings({"api_key": "sk_test1234", "model": "eleven_v4", "voice": VIVIAN}, "zh")
    api.sent.clear()
    return api


# ---------------------------------------------------------------- the API

def test_speakable_removes_what_would_be_audio_tags():
    assert elevenlabs_tts.speakable("在[zai4]陽明山[yang2 ming2 shan1]上，\n老鷹[lao3 ying1]") == "在陽明山上， 老鷹"
    assert elevenlabs_tts.speakable("[laughs]") == elevenlabs_tts.speakable("……") == ""


def test_synthesize_sends_the_key_model_and_clean_text(api):
    assert ElevenLabs("sk_x").synthesize_mp3("老鷹[lao3 ying1]盤旋", VIVIAN, "eleven_v4") == b"mp3"
    assert api.sent == [{"path": f"/v1/text-to-speech/{VIVIAN}", "key": "sk_x",
                         "url": f"{elevenlabs_tts.API}/v1/text-to-speech/{VIVIAN}?output_format=mp3_44100_128",
                         "body": {"text": "老鷹盤旋", "model_id": "eleven_v4"}}]
    with pytest.raises(ElevenLabsError, match="nothing"):
        ElevenLabs("sk_x").synthesize_mp3("[whispers]", VIVIAN, "eleven_v4")
    with pytest.raises(ElevenLabsError, match="API key"):
        ElevenLabs("")


@pytest.mark.parametrize("refusal, message", [
    (_refusal(401, "quota_exceeded"), "credits are used up"),
    (_refusal(401, "missing_permissions", "missing the permission models_read"), "missing a permission: .*models_read"),
    (_refusal(402, "payment_required", "Free users cannot use library voices via the API."), "Free users"),
    (_refusal(401, "invalid_api_key", "Invalid API key"), "refused the API key"),
])
def test_refusals_are_explained(api, refusal, message):
    api.answers["/v1/models"] = refusal
    with pytest.raises(ElevenLabsError, match=message):
        ElevenLabs("sk_x").models()
    assert len(api.sent) == 1  # not tried again


def test_busy_and_timeouts_are_tried_again(api):
    api.answers["/v1/user/subscription"] = [_refusal(503, "busy"), TimeoutError("read timed out"),
                                            json.dumps({"character_count": 6497, "character_limit": 39622}).encode()]
    assert ElevenLabs("sk_x").credits() == {"used": 6497, "limit": 39622, "reset": None}
    api.answers["/v1/user/subscription"] = TimeoutError("read timed out")
    with pytest.raises(ElevenLabsError, match="didn't answer"):
        ElevenLabs("sk_x").credits()


def test_models_that_read(api):
    api.answers["/v1/models"] = json.dumps([
        {"model_id": "eleven_v4", "name": "Eleven v4", "can_do_text_to_speech": True,
         "model_rates": {"character_cost_multiplier": 1.0}, "languages": [{"language_id": "zh"}]},
        {"model_id": "eleven_english_sts_v2", "name": "Eleven English v2", "can_do_text_to_speech": False},
    ]).encode()
    assert ElevenLabs("sk_x").models() == [{"id": "eleven_v4", "name": "Eleven v4", "languages": ["zh"]}]


def test_chapter_read_sentence_by_sentence(api, monkeypatch, tmp_path):
    encoded = []
    monkeypatch.setattr(elevenlabs_tts, "encode_mp3", lambda samples, rate, path: encoded.append((len(samples), rate)))
    second = np.zeros(elevenlabs_tts.PCM_RATE, dtype="<i2").tobytes()  # one second of PCM
    api.answers[f"/v1/text-to-speech/{VIVIAN}"] = second
    timed = ElevenLabs("sk_x").synthesize_chapter(["你好。", "……", "再見。"], VIVIAN, "eleven_v4", tmp_path / "c.mp3")
    assert timed == pytest.approx([(0.0, 1.0, "你好。……"), (1.3, 2.3, "再見。")])
    assert "output_format=pcm_24000" in api.sent[0]["url"] and len(api.sent) == 2
    assert encoded == [(int(2.6 * elevenlabs_tts.PCM_RATE), elevenlabs_tts.PCM_RATE)]


# ---------------------------------------------------------------- the voices offered

def test_not_offered_until_set_up(api):
    anki.save_config({"tts_use_edge": True})
    elevenlabs.save_settings({"voice": VIVIAN}, "zh")  # no key
    assert "zh-ElevenLabs" not in {v["id"] for v in sentence_tts.voices("zh")["voices"]}


def test_offered_last_and_never_by_default(set_up):
    zh = sentence_tts.voices("zh")
    assert zh["voices"][-1] == {"id": "zh-ElevenLabs", "label": "ElevenLabs - Vivian (uses credits)"}
    assert zh["default"] == "zh-TW-HsiaoChenNeural"
    assert "ja-ElevenLabs" not in {v["id"] for v in sentence_tts.voices("ja")["voices"]}  # no Japanese voice
    anki.save_config({"tts_voices": {"zh": "zh-ElevenLabs"}})  # chosen before it stopped being the main voice
    assert sentence_tts.default_voice("zh") == "zh-TW-HsiaoChenNeural"
    anki.save_config({"tts_use_edge": False})  # no other voice: still not read by it unless asked
    assert sentence_tts.voices("zh")["default"] == ""
    assert language_options(Language.MANDARIN_TW)["default_voice"] == ""


def test_main_voice(set_up):
    anki.save_config({"tts_voices": {"ja": ""}})  # Japanese sentences read by hand
    elevenlabs.save_settings({"voice": "jaVoice"}, "ja")
    elevenlabs.save_settings({"main": True}, "zh")
    assert sentence_tts.voices("zh")["voices"][0]["id"] == sentence_tts.voices("zh")["default"] == "zh-ElevenLabs"
    assert sentence_tts.default_voice("zh") == "zh-ElevenLabs"
    assert sentence_tts.default_voice("ja") == ""  # kept
    assert language_options(Language.MANDARIN_TW)["default_voice"] == "ElevenLabs - Vivian (uses credits)"
    elevenlabs.save_settings({"main": False}, "zh")
    assert sentence_tts.default_voice("zh") == "zh-TW-HsiaoChenNeural"
    assert "zh" not in anki.get_config()["tts_voices"]


def test_latest_model_by_default(set_up):
    set_up.answers["/v1/models"] = json.dumps([
        {"model_id": "eleven_v9_en", "can_do_text_to_speech": True, "languages": [{"language_id": "en"}]},
        {"model_id": "eleven_v8", "can_do_text_to_speech": True, "languages": [{"language_id": "zh"}]},
        {"model_id": "eleven_v7", "can_do_text_to_speech": True, "languages": [{"language_id": "zh"}]},
    ]).encode()
    assert elevenlabs.model("zh") == "eleven_v4"  # the one chosen
    elevenlabs.save_settings({"model": ""}, "zh")
    assert elevenlabs.get_settings()["model"] == elevenlabs.LATEST
    assert elevenlabs.model("zh") == "eleven_v8"  # the latest reading Mandarin
    assert elevenlabs.model("ar") == "eleven_v9_en"  # none lists it: the latest
    elevenlabs.model("zh")
    assert [r["path"] for r in set_up.sent].count("/v1/models") == 2  # asked once per language
    sentence_tts.synthesize("zh", "你好", "zh-ElevenLabs")
    assert set_up.sent[-1]["body"]["model_id"] == "eleven_v8"
    assert elevenlabs.save_settings({"api_key": "sk_new"}, "zh") and elevenlabs.get_settings()["model"] == elevenlabs.LATEST


def test_cards_read_by_it(set_up):
    speech = sentence_tts.synthesize("zh", "在[zai4]陽明山上", "zh-ElevenLabs")
    assert speech == sentence_tts.Speech(b"mp3")
    assert set_up.sent[0]["body"] == {"text": "在陽明山上", "model_id": "eleven_v4"}
    assert set_up.sent[0]["path"] == f"/v1/text-to-speech/{VIVIAN}"
    set_up.answers[f"/v1/text-to-speech/{VIVIAN}"] = _refusal(401, "quota_exceeded")
    with pytest.raises(sentence_tts.TtsError, match="credits are used up"):
        sentence_tts.synthesize("zh", "在陽明山上", "zh-ElevenLabs")


def test_books_read_by_it(set_up, monkeypatch, tmp_path):
    read = []
    monkeypatch.setattr(ElevenLabs, "synthesize_chapter",
                        lambda self, sentences, voice, model, path: read.append((sentences, voice, model)) or [(0, 1, "你好。")])
    n = speech_synthesis._synthesize_chapter("你好。", "zh-ElevenLabs", Language.MANDARIN_TW, tmp_path / "c.mp3",
                                             tmp_path / "c.srt", anki.get_config())
    assert n == 1 and read == [(["你好。"], VIVIAN, "eleven_v4")]
    elevenlabs.save_settings({"voice": ""}, "zh")
    with pytest.raises(ConverterError, match="Settings › Voice"):
        speech_synthesis._synthesize_chapter("你好。", "zh-ElevenLabs", Language.MANDARIN_TW, tmp_path / "c.mp3",
                                             tmp_path / "c.srt", anki.get_config())


# ---------------------------------------------------------------- the settings page

@pytest.fixture
def client():
    from miningcat.interfaces.web import app as web_app
    from miningcat.interfaces.web.jobs import AppState
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_http_settings_never_give_the_key_back(client, api):
    res = client.post("/api/tts/elevenlabs", json={"language": "zh", "api_key": " sk_secret9876 ", "voice": VIVIAN},
                      headers=HEADERS).get_json()
    assert res["has_key"] and res["key_hint"] == "…9876" and res["voice"] == VIVIAN
    assert res["voice_name"] == ""  # the fake API has no name for it
    page = client.get("/api/tts/elevenlabs?language=zh").get_json()
    assert "sk_secret9876" not in json.dumps(page) and "sk_secret9876" not in json.dumps(client.get("/api/anki/config").get_json())
    assert elevenlabs.get_settings()["api_key"] == "sk_secret9876"
    assert client.get("/api/tts/elevenlabs?language=ja").get_json()["voice"] == ""
    key_id = "547" + "0" * 61  # what ElevenLabs' list of keys shows
    res = client.post("/api/tts/elevenlabs", json={"language": "zh", "api_key": key_id}, headers=HEADERS)
    assert res.status_code == 400 and "start with 'sk_'" in res.get_json()["error"]
    assert elevenlabs.get_settings()["api_key"] == "sk_secret9876"  # kept


def test_http_account(client, set_up):
    set_up.answers["/v1/models"] = json.dumps([]).encode()
    set_up.answers["/v1/user/subscription"] = json.dumps({"character_count": 1, "character_limit": 10}).encode()
    assert client.get("/api/tts/elevenlabs/account").get_json() == {
        "models": [], "credits": {"used": 1, "limit": 10, "reset": None}}
    set_up.answers["/v1/models"] = _refusal(401, "missing_permissions", "models_read")
    res = client.get("/api/tts/elevenlabs/account")
    assert res.status_code == 400 and "models_read" in res.get_json()["error"]


# ---------------------------------------------------------------- the key, encrypted

def _stored_key() -> str:
    from miningcat.infrastructure.persistence.settings_store import settings
    return settings.get("elevenlabs")["api_key"]


def test_key_encrypted_in_the_database(api):
    from miningcat.config.paths import paths
    elevenlabs.save_settings({"api_key": "sk_secret9876"}, "zh")
    assert _stored_key().startswith("fernet:") and "sk_secret9876" not in _stored_key()
    assert elevenlabs.get_settings()["api_key"] == "sk_secret9876"
    assert paths.secret_key.exists()
    if os.name == "posix":
        assert paths.secret_key.stat().st_mode & 0o077 == 0  # the user's only


def test_key_saved_in_clear_is_encrypted(api):
    from miningcat.infrastructure.persistence.settings_store import settings
    settings.set("elevenlabs", {"api_key": "sk_old", "model": "eleven_v4"})  # before keys were encrypted
    assert elevenlabs.get_settings()["api_key"] == "sk_old"
    assert _stored_key().startswith("fernet:")
    assert elevenlabs.get_settings()["model"] == "eleven_v4"


def test_key_file_lost(api):
    from miningcat.config.paths import paths
    elevenlabs.save_settings({"api_key": "sk_secret9876", "voice": VIVIAN}, "zh")
    key_file = paths.secret_key.read_bytes()
    paths.secret_key.unlink()
    page = elevenlabs.public_settings("zh")
    assert not page["has_key"] and "secret.key" in page["key_error"]
    assert elevenlabs.voice("zh") == ""  # not offered
    elevenlabs.save_settings({"main": True}, "zh")  # the encrypted key is kept...
    paths.secret_key.write_bytes(key_file)
    assert elevenlabs.get_settings()["api_key"] == "sk_secret9876"  # ...and read again with its key file
    paths.secret_key.unlink()
    elevenlabs.save_settings({"api_key": "sk_new"}, "zh")  # or replaced
    assert elevenlabs.get_settings()["api_key"] == "sk_new"
