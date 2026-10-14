"""Text-to-speech with ElevenLabs (online, paid: each character read uses the account's credits). The user brings their
own API key, the model, and a voice per study language (its id, copied from the voice library of elevenlabs.io).

The key needs these permissions: Text to Speech (to read), Models (read, to list the models) and User (read, to
show the credits left). Voices (read) is optional: it gives the voice's name. A free account can't use the voices of
the library through the API: ElevenLabs answers that a paid plan is needed.

The models v3 and newer read text in square brackets as audio tags ([whispers], [laughs]...): the readings written
in brackets (字[zi4]) are removed before the text is sent."""

import json
import re
import time
import urllib.error
import urllib.request

import numpy as np

from miningcat.infrastructure.http import USER_AGENT, ssl_context
from miningcat.infrastructure.speech.local_models import encode_mp3

API = "https://api.elevenlabs.io"
KEY_PREFIX = "sk_"
PERMISSIONS = ("Text to Speech", "Models: read", "User: read")
VOICE_LIBRARY_URL = "https://elevenlabs.io/app/voice-library"
PCM_RATE = 24000  # the PCM ElevenLabs gives on every plan (44.1 kHz needs a Pro one)
PAUSE_SECONDS = 0.3  # silence between two sentences of a chapter
RETRIES = 4
TIMEOUT_S = 120

VOICE_SUFFIX = "-ElevenLabs"


class ElevenLabsError(RuntimeError):
    pass


def voice_id(language: str) -> str:
    """The id MiningCat gives to the ElevenLabs voice of a study language: "zh-ElevenLabs". Like Edge's, it starts
    with the language. The voice's id at ElevenLabs is in the settings."""
    return language + VOICE_SUFFIX


def is_voice(voice: str) -> bool:
    return voice.endswith(VOICE_SUFFIX)


def voice_language(voice: str) -> str:
    """"zh-ElevenLabs" -> "zh"."""
    return voice[:-len(VOICE_SUFFIX)]


def speakable(text: str) -> str:
    """The text without what ElevenLabs would read as audio tags: anything in square brackets (readings). "" when
    nothing is left to read but punctuation."""
    text = re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", text)).strip()
    return text if any(c.isalnum() for c in text) else ""


def _message(code: int, body: bytes) -> str:
    """What the user is told when ElevenLabs refuses a request."""
    try:
        detail = json.loads(body).get("detail")
    except (ValueError, AttributeError):
        detail = None
    if not isinstance(detail, dict):
        detail = {"message": str(detail or body.decode(errors="replace")[:300])}
    status, message = detail.get("status") or detail.get("code") or "", detail.get("message") or ""
    if status == "quota_exceeded":
        return "Your ElevenLabs credits are used up: add some on elevenlabs.io, or pick another voice."
    if status == "missing_permissions":
        return f"The ElevenLabs API key is missing a permission: {message}"
    if status in ("invalid_api_key", "unauthorized") or code == 401:
        return f"ElevenLabs refused the API key: {message or 'check it in Settings › Voice.'}"
    if status == "voice_not_found" or code == 404:
        return "ElevenLabs doesn't know this voice: check its id in Settings › Voice."
    return f"ElevenLabs: {message or f'error {code}'}"


class ElevenLabs:
    """The ElevenLabs API, with the user's key."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ElevenLabsError("Add your ElevenLabs API key in Settings › Voice first.")
        self._key = api_key

    def _request(self, path: str, body: dict | None = None) -> bytes:
        request = urllib.request.Request(
            API + path, data=json.dumps(body).encode() if body is not None else None,
            headers={"xi-api-key": self._key, "Content-Type": "application/json", "User-Agent": USER_AGENT})
        for attempt in range(RETRIES + 1):
            try:
                return _send(request)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                    raise ElevenLabsError(_message(exc.code, exc.read())) from exc
            except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
                if attempt == RETRIES:
                    raise ElevenLabsError(f"ElevenLabs didn't answer: {getattr(exc, 'reason', exc)}") from exc
            time.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    def _json(self, path: str):
        try:
            return json.loads(self._request(path))
        except ValueError as exc:
            raise ElevenLabsError(f"ElevenLabs gave an unexpected answer to {path}.") from exc

    def models(self) -> list[dict]:
        """The models that read text: [{id, name, languages: [key]}], the latest first (as ElevenLabs lists them)."""
        return [{"id": m["model_id"], "name": m.get("name") or m["model_id"],
                 "languages": [lang["language_id"] for lang in m.get("languages") or []]}
                for m in self._json("/v1/models") if m.get("can_do_text_to_speech")]

    def credits(self) -> dict:
        """{used, limit, reset (Unix time)} of the account's credits."""
        sub = self._json("/v1/user/subscription")
        return {"used": sub.get("character_count"), "limit": sub.get("character_limit"),
                "reset": sub.get("next_character_count_reset_unix")}

    def voice_name(self, voice: str) -> str:
        """The name of a voice (needs the Voices: read permission)."""
        return self._json(f"/v1/voices/{voice}").get("name") or ""

    def _speech(self, text: str, voice: str, model: str, output_format: str) -> bytes:
        text = speakable(text)
        if not text:
            raise ElevenLabsError("There's nothing ElevenLabs can read in this text.")
        audio = self._request(f"/v1/text-to-speech/{voice}?output_format={output_format}",
                              {"text": text, "model_id": model})
        if not audio:
            raise ElevenLabsError("ElevenLabs returned no audio.")
        return audio

    def synthesize_mp3(self, text: str, voice: str, model: str) -> bytes:
        """The MP3 of the text read by the voice."""
        return self._speech(text, voice, model, "mp3_44100_128")

    def synthesize_samples(self, text: str, voice: str, model: str) -> np.ndarray:
        """The text read by the voice, as mono float32 samples at PCM_RATE."""
        pcm = self._speech(text, voice, model, f"pcm_{PCM_RATE}")
        return np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768

    def synthesize_chapter(self, sentences: list[str], voice: str, model: str,
                           audio_path) -> list[tuple[float, float, str]]:
        """Reads the sentences one after the other into an MP3 file. Returns the (start, end, sentence) of each."""
        pieces, timed, position = [], [], 0.0
        for sentence in sentences:
            if not speakable(sentence):
                if timed:  # punctuation alone: shown with the sentence before
                    timed[-1] = (*timed[-1][:2], timed[-1][2] + sentence)
                continue
            samples = self.synthesize_samples(sentence, voice, model)
            duration = len(samples) / PCM_RATE
            timed.append((position, position + duration, sentence))
            pieces += [samples, np.zeros(int(PAUSE_SECONDS * PCM_RATE), dtype=np.float32)]
            position += duration + PAUSE_SECONDS
        if not pieces:
            raise ElevenLabsError("There's nothing ElevenLabs can read in this text.")
        encode_mp3(np.concatenate(pieces), PCM_RATE, audio_path)
        return timed


def _send(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=ssl_context()) as response:
        return response.read()
