import shutil
import subprocess

import pytest

pytest.importorskip("flask")

from web import app as web_app
from web import book_audio, books
from web.state import AppState

HEADERS = {"X-MiningCat": "1"}

SRT_1 = """1
00:00:00,000 --> 00:00:02,500
他說話很快，

2
00:00:02,500 --> 00:00:04,000
我們都聽不懂。

3
00:00:04,000 --> 00:00:07,250
今天天氣很好。
"""
SRT_2 = """1
00:00:01,000 --> 00:00:03,000
I went to the market yesterday.

2
00:00:03,000 --> 00:00:05,000
It was very busy.
"""
BOOK = "第1章\n\n他說話很快，我們都聽不懂。今天天氣很好。\n"


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "DIR_LIBRARY", tmp_path / "library")
    book_audio._index.clear()
    book_audio._chapter_track.clear()
    return tmp_path / "library"


@pytest.fixture
def output(tmp_path):
    audio_dir, srt_dir = tmp_path / "output" / "chapters_audio", tmp_path / "output" / "srt"
    audio_dir.mkdir(parents=True)
    srt_dir.mkdir(parents=True)
    for name, srt in (("chapter_001", SRT_1), ("chapter_002", SRT_2)):
        (audio_dir / f"{name}.mp3").write_bytes(b"ID3 fake audio " + name.encode())
        (srt_dir / f"{name}.srt").write_text(srt, encoding="utf-8")
    (audio_dir / "chapter_003.mp3").write_bytes(b"no subtitles")
    return audio_dir, srt_dir


@pytest.fixture
def book(library):
    return books.import_book("夜市.txt", BOOK.encode("utf-8"))["id"]


def test_parse_srt():
    cues = book_audio.parse_srt(SRT_1.replace("\n", "\r\n") + "\n4\n00:00:08,000 --> 00:00:09,000\n<i>好</i>\n")
    assert [(c.start, c.end, c.text) for c in cues][0] == (0.0, 2.5, "他說話很快，")
    assert cues[-1].text == "好"


def test_output_tracks_pair_audio_and_subtitles(output):
    pairs = book_audio.output_tracks(*output)
    assert [(a.name, s.name) for a, s in pairs] == [("chapter_001.mp3", "chapter_001.srt"), ("chapter_002.mp3", "chapter_002.srt")]


def test_attach_and_find_sentences(book, output):
    assert book_audio.info(book) is None
    info = book_audio.attach(book, book_audio.output_tracks(*output))
    assert info["tracks"] == 2 and info["names"] == ["chapter_001", "chapter_002"]
    # a sentence spanning two cues, punctuation and spaces ignored
    assert book_audio.find_sentence(book, "他說話很快，我們都聽不懂。", chapter=0, language="zh") == {"track": 0, "start": 0.0, "end": 4.0}
    # the subtitles may be in the other script
    assert book_audio.find_sentence(book, "今天天气很好", language="zh") == {"track": 0, "start": 4.0, "end": 7.25}
    assert book_audio.find_sentence(book, "It was very BUSY!") == {"track": 1, "start": 3.0, "end": 5.0}
    # a transcription that differs a little from the book
    assert book_audio.find_sentence(book, "I went to a market yesterday") == {"track": 1, "start": 1.0, "end": 3.0}
    assert book_audio.find_sentence(book, "Something else entirely, nowhere in the audio.") is None
    assert book_audio.find_sentence(book, "。。") is None
    assert book_audio.track_path(book, 1).read_bytes().endswith(b"chapter_002")


def test_attach_needs_converted_audio(book, tmp_path):
    with pytest.raises(book_audio.AudioError, match="No converted audio"):
        book_audio.attach(book, [])


def test_remove_audio(book, output):
    book_audio.attach(book, book_audio.output_tracks(*output))
    book_audio.remove(book)
    assert book_audio.info(book) is None
    with pytest.raises(book_audio.AudioError):
        book_audio.find_sentence(book, "他說話很快")
    with pytest.raises(book_audio.AudioError):
        book_audio.track_path(book, 0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_clip_cuts_mp3(book, tmp_path):
    audio = tmp_path / "tone.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", str(audio)], check=True)
    srt = tmp_path / "tone.srt"
    srt.write_text(SRT_1, encoding="utf-8")
    book_audio.attach(book, [(audio, srt)])
    data = book_audio.clip(book, 0, 1.0, 2.0)
    assert data[:3] == b"ID3" or data[:2] == b"\xff\xfb"
    with pytest.raises(book_audio.AudioError, match="Invalid"):
        book_audio.clip(book, 0, 3, 1)


def test_clip_reports_ffmpeg_errors(book, output, monkeypatch):
    book_audio.attach(book, book_audio.output_tracks(*output))

    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(book_audio.subprocess, "run", missing)
    with pytest.raises(book_audio.AudioError, match="ffmpeg isn't installed"):
        book_audio.clip(book, 0, 0, 1)

    def failing(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"broken file")

    monkeypatch.setattr(book_audio.subprocess, "run", failing)
    with pytest.raises(book_audio.AudioError, match="broken file"):
        book_audio.clip(book, 0, 0, 1)


# ---------------------------------------------------------------- HTTP

@pytest.fixture
def client(library, tmp_path, monkeypatch, output):
    import config
    from web import files
    monkeypatch.setattr(files, "ROOT", tmp_path)
    monkeypatch.setattr(files, "DIR_SOURCES", tmp_path / "sources")
    monkeypatch.setattr(files, "DIR_STAGING", tmp_path / "sources" / ".staging")
    monkeypatch.setattr(config, "DIR_CHAPTERS_AUDIO", output[0])
    monkeypatch.setattr(config, "DIR_SRT", output[1])
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def test_http_audio_of_a_book(client, book, monkeypatch):
    base = f"/reader/api/books/{book}/audio"
    assert client.get(base).get_json() == {"audio": None}
    assert client.post(f"{base}/find", json={"sentence": "x"}, headers=HEADERS).status_code == 400

    assert client.post(f"{base}/link", json={}, headers=HEADERS).get_json()["audio"]["tracks"] == 2
    found = client.post(f"{base}/find", json={"sentence": "我們都聽不懂", "chapter": 0}, headers=HEADERS).get_json()
    assert found == {"found": True, "url": f"{base}/0", "track": 0, "start": 2.5, "end": 4.0}
    assert client.post(f"{base}/find", json={"sentence": "nothing like it"}, headers=HEADERS).get_json() == {"found": False}
    assert client.get(f"{base}/0").data.startswith(b"ID3 fake audio")
    assert client.get(f"{base}/0", headers={"Range": "bytes=0-2"}).status_code == 206

    monkeypatch.setattr(book_audio, "clip", lambda book_id, track, start, end: b"MP3")
    clipped = client.post(f"{base}/clip", json={"sentence": "今天天氣很好"}, headers=HEADERS).get_json()
    assert clipped["data"] == "data:audio/mpeg;base64,TVAz" and clipped["start"] == 4.0
    assert client.post(f"{base}/clip", json={"sentence": "nothing like it"}, headers=HEADERS).get_json() == {"found": False}

    assert client.post(f"{base}/delete", json={}, headers=HEADERS).get_json() == {"audio": None}
    assert client.get(base).get_json() == {"audio": None}


def test_http_reader_from_a_conversion(client, tmp_path):
    staged = tmp_path / "sources" / ".staging" / "ebook"
    staged.mkdir(parents=True)
    (staged / "夜市.txt").write_text(BOOK, encoding="utf-8")
    res = client.post("/api/reader/from-output", json={"ebook": ["sources/.staging/ebook/夜市.txt"]}, headers=HEADERS)
    data = res.get_json()
    assert res.status_code == 200, data
    assert data["audio"]["tracks"] == 2
    assert books.get_meta(data["id"])["title"] == "夜市"
    assert client.post("/api/reader/from-output", json={"ebook": []}, headers=HEADERS).status_code == 400
