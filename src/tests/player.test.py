import io
import shutil
import subprocess

import pytest

pytest.importorskip("flask")

from web import app as web_app
from web import books, videos
from web.state import AppState

HEADERS = {"X-MiningCat": "1"}
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg isn't installed")

JA_SRT = """1
00:00:00,200 --> 00:00:01,200
吾輩は猫である。

2
00:00:01,400 --> 00:00:02,600
{\\an8}名前は
まだ無い。
"""

EN_VTT = """WEBVTT

00:00.500 --> 00:01.500
I am a cat.

00:01.600 --> 00:02.800
<i>No name yet.</i>
"""


def make_video(path, codec="h264", subtitles=None):
    """A 3 second test video: h264 + AAC in MP4 (plays as it is), or MPEG-4 + MP3 in AVI (needs a copy)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3",
           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=22050:duration=3"]
    if subtitles:
        cmd += ["-i", str(subtitles)]
    cmd += ["-map", "0:v", "-map", "1:a"] + (["-map", "2:s", "-c:s", "srt"] if subtitles else [])
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"] if codec == "h264" else ["-c:v", "mpeg4", "-c:a", "libmp3lame"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "DIR_LIBRARY", tmp_path / "library")
    # preparations run right away instead of in a thread
    monkeypatch.setattr(videos, "_spawn", lambda target, *args: target(*args))
    return tmp_path / "library"


@pytest.fixture
def client(library, tmp_path, monkeypatch):
    from web import files
    monkeypatch.setattr(files, "ROOT", tmp_path)
    app = web_app.create_app(AppState())
    app.testing = True
    return app.test_client()


def upload(client, path):
    return client.post(f"/player/api/videos?name={path.name}", data=path.read_bytes(), headers=HEADERS)


# ---------------------------------------------------------------- browser copy

H264_AAC = {"video_codec": "h264", "audio": [{"codec": "aac"}, {"codec": "ac3"}]}


def test_play_plan_original_plays_as_it_is():
    assert videos.play_plan("mp4", H264_AAC) is None
    assert videos.play_plan("mkv", {"video_codec": "vp9", "audio": [{"codec": "opus"}]}) is None
    assert videos.play_plan("mp4", {"video_codec": None, "audio": [{"codec": "aac"}]}) is None


def test_play_plan_copies_what_it_can():
    # unsupported container: remuxed without re-encoding
    assert videos.play_plan("avi", H264_AAC) == {"video": "copy", "audio": "copy", "audio_track": 0, "hevc": False, "scale": False}
    # AC3 audio: only the audio is encoded again
    assert videos.play_plan("mkv", {"video_codec": "h264", "audio": [{"codec": "ac3"}]})["audio"] == "aac"
    # another audio track than the first one: the browser can't switch tracks
    plan = videos.play_plan("mp4", H264_AAC, audio_track=1)
    assert plan == {"video": "copy", "audio": "aac", "audio_track": 1, "hevc": False, "scale": False}
    assert videos.play_plan("avi", {"video_codec": "mpeg4", "audio": [{"codec": "mp3"}]})["video"] == "h264"


HEVC_MKV = {"video_codec": "hevc", "width": 1920, "height": 1080, "audio": [{"codec": "mp3"}, {"codec": "opus"}]}


def test_play_plan_levels():
    # the browser couldn't play the MKV: first the same streams in an MP4 (Safari plays HEVC, not MKV)
    assert videos.play_plan("mkv", HEVC_MKV) is None
    assert videos.play_plan("mkv", HEVC_MKV, level="remux") == {
        "video": "copy", "audio": "copy", "audio_track": 0, "hevc": True, "scale": False}
    # then the video encoded again; the audio stays as it is when it can
    plan = videos.play_plan("mkv", HEVC_MKV, level="encode")
    assert plan["video"] == "h264" and plan["audio"] == "copy" and not plan["scale"]
    assert videos.play_plan("mkv", {**HEVC_MKV, "width": 3840, "height": 2160}, level="encode")["scale"]


def test_encode_command():
    plan = videos.play_plan("mkv", {**HEVC_MKV, "width": 3840, "height": 2160}, level="encode")
    cmd = videos._ffmpeg_command(videos.Path("in.mkv"), videos.Path("out.mp4"), plan)
    assert cmd[cmd.index("-hwaccel") + 1] == "auto" and cmd.index("-hwaccel") < cmd.index("-i")
    assert cmd[cmd.index("-preset") + 1] == videos.ENCODE_PRESET
    assert "1920" in cmd[cmd.index("-vf") + 1]
    remux = videos._ffmpeg_command(videos.Path("in.mkv"), videos.Path("out.mp4"), videos.play_plan("mkv", HEVC_MKV, level="remux"))
    assert "-hwaccel" not in remux and remux[remux.index("-tag:v") + 1] == "hvc1"


# ---------------------------------------------------------------- subtitles

def test_parse_subtitles_cleans_text():
    cues = videos.parse_subtitles(JA_SRT)
    assert cues == [
        {"start": 0.2, "end": 1.2, "text": "吾輩は猫である。"},
        {"start": 1.4, "end": 2.6, "text": "名前は まだ無い。"},
    ]


@needs_ffmpeg
def test_subtitle_tracks(client, tmp_path):
    video_id = upload(client, make_video(tmp_path / "neko.mp4")).get_json()["video"]["id"]
    res = client.post(f"/player/api/videos/{video_id}/subtitles", headers=HEADERS, data={
        "files": [(io.BytesIO(JA_SRT.encode("utf-8")), "neko.ja.srt"),
                  (io.BytesIO(EN_VTT.encode("utf-8")), "neko.en.vtt"),
                  (io.BytesIO(b"nothing"), "notes.txt")],
    }, content_type="multipart/form-data")
    data = res.get_json()
    assert [t["label"] for t in data["added"]] == ["neko.ja", "neko.en"]
    assert data["errors"] and "notes.txt" in data["errors"][0]
    ja, en = data["added"]
    cues = client.get(f"/player/api/videos/{video_id}/subtitles/{en['id']}").get_json()["cues"]
    assert cues == [{"start": 0.5, "end": 1.5, "text": "I am a cat."}, {"start": 1.6, "end": 2.8, "text": "No name yet."}]

    # the same subtitles again aren't added twice
    assert videos.add_subtitles(video_id, "again.srt", JA_SRT.encode())["id"] == ja["id"]

    client.post(f"/player/api/videos/{video_id}/prefs", json={"primary": ja["id"], "secondary": en["id"]}, headers=HEADERS)
    res = client.post(f"/player/api/videos/{video_id}/subtitles/{en['id']}/delete", headers=HEADERS).get_json()
    assert [t["id"] for t in res["tracks"]] == [ja["id"]]
    assert res["prefs"]["secondary"] == "" and res["prefs"]["primary"] == ja["id"]
    assert client.get(f"/player/api/videos/{video_id}/subtitles/{en['id']}").status_code == 400


# ---------------------------------------------------------------- import & playback

@needs_ffmpeg
def test_upload_mp4_plays_as_it_is(client, library, tmp_path):
    source = make_video(tmp_path / "neko.mp4")
    meta = upload(client, source).get_json()["video"]
    assert meta["status"] == "ready" and meta["title"] == "neko"
    assert meta["video_codec"] == "h264" and meta["duration"] == pytest.approx(3, abs=0.2)
    folder = library / "videos" / meta["id"]
    assert (folder / "source.mp4").exists() and not (folder / "play.mp4").exists()
    assert (folder / "thumb.jpg").exists()

    # the same file again is the same video
    assert upload(client, source).get_json()["video"]["id"] == meta["id"]
    listed = client.get("/player/api/videos").get_json()["videos"]
    assert [v["id"] for v in listed] == [meta["id"]]

    # seeking needs range requests
    res = client.get(f"/player/api/videos/{meta['id']}/file", headers={"Range": "bytes=0-99"})
    assert res.status_code == 206 and len(res.data) == 100
    assert client.get(f"/player/api/videos/{meta['id']}/thumb").status_code == 200


@needs_ffmpeg
def test_upload_avi_gets_a_browser_copy(client, library, tmp_path):
    meta = upload(client, make_video(tmp_path / "old.avi", codec="mpeg4")).get_json()["video"]
    assert meta["status"] == "ready", meta.get("error")
    play = library / "videos" / meta["id"] / "play.mp4"
    assert play.exists()
    assert videos.probe(play)["video_codec"] == "h264"
    assert client.get(f"/player/api/videos/{meta['id']}/file").mimetype == "video/mp4"


@needs_ffmpeg
def test_embedded_subtitles_and_language(client, tmp_path):
    srt = tmp_path / "subs.srt"
    # enough kana to tell the language
    srt.write_text(JA_SRT + "\n3\n00:00:02,700 --> 00:00:02,900\nどこで生れたかとんと見当がつかぬ。ひらがなとカタカナのテストです。\n",
                   encoding="utf-8")
    meta = upload(client, make_video(tmp_path / "neko.mkv", subtitles=srt)).get_json()["video"]
    assert meta["status"] == "ready"
    assert len(meta["tracks"]) == 1 and meta["tracks"][0]["origin"] == "embedded"
    assert meta["language"] == "ja"
    cues = videos.cues(meta["id"], meta["tracks"][0]["id"])
    assert cues[0]["text"] == "吾輩は猫である。"


def clip_seconds(client, video_id, start, end, tmp_path, **extra):
    import base64
    data = client.post(f"/player/api/videos/{video_id}/clip", json={"start": start, "end": end, **extra}, headers=HEADERS).get_json()
    mime = "audio/wav" if extra.get("format") == "wav" else "audio/mpeg"
    assert data["data"].startswith(f"data:{mime};base64,")
    mp3 = tmp_path / "clip.mp3"
    mp3.write_bytes(base64.b64decode(data["data"].split(",", 1)[1]))
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
                                capture_output=True, check=True, text=True).stdout)


@needs_ffmpeg
def test_several_embedded_tracks(client, tmp_path):
    ja, en = tmp_path / "ja.srt", tmp_path / "en.srt"
    ja.write_text(JA_SRT, encoding="utf-8")
    en.write_text("1\n00:00:00,500 --> 00:00:01,500\nI am a cat.\n", encoding="utf-8")
    target = tmp_path / "two.mkv"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=3", "-i", str(ja), "-i", str(en),
                    "-map", "0:v", "-map", "1", "-map", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:s", "srt",
                    "-metadata:s:s:0", "title=Japanese", "-metadata:s:s:1", "language=eng", str(target)], check=True)
    calls = []
    real_run = subprocess.run
    monkey = pytest.MonkeyPatch()
    monkey.setattr(videos.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or real_run(cmd, **kw))
    try:
        meta = upload(client, target).get_json()["video"]
    finally:
        monkey.undo()
    assert [(t["label"], t["cues"]) for t in meta["tracks"]] == [("Japanese", 2), ("eng", 1)]
    extractions = [c for c in calls if "-c:s" in c]
    assert len(extractions) == 1  # both tracks in one read of the file


@needs_ffmpeg
def test_clip(client, tmp_path):
    video_id = upload(client, make_video(tmp_path / "neko.mp4")).get_json()["video"]["id"]
    # the whole line, with 200 ms before and after by default
    measured = clip_seconds(client, video_id, 0.5, 1.5, tmp_path)
    assert measured == pytest.approx(1.4, abs=0.1), measured  # MP3 frames add a few ms
    client.post("/player/api/settings", json={"audio_before": 0, "audio_after": 1000}, headers=HEADERS)
    assert clip_seconds(client, video_id, 0.5, 1.5, tmp_path) == pytest.approx(2.0, abs=0.1)
    # several lines: one span
    assert clip_seconds(client, video_id, 0.5, 1.9, tmp_path) == pytest.approx(2.4, abs=0.1)
    res = client.post(f"/player/api/videos/{video_id}/clip", json={"start": "x"}, headers=HEADERS)
    assert res.status_code == 400
    # the span chosen on the card creator's waveform: as is, without the margins; the waveform itself as WAV
    assert clip_seconds(client, video_id, 0.3, 1.8, tmp_path, exact=True) == pytest.approx(1.5, abs=0.1)
    assert clip_seconds(client, video_id, 0.3, 1.8, tmp_path, exact=True, format="wav") == pytest.approx(1.5, abs=0.01)
    res = client.post(f"/player/api/videos/{video_id}/clip", json={"start": 0, "end": 600}, headers=HEADERS)
    assert res.status_code == 400


@needs_ffmpeg
def test_frame(client, tmp_path):
    import base64
    video_id = upload(client, make_video(tmp_path / "neko.mp4")).get_json()["video"]["id"]
    data = client.post(f"/player/api/videos/{video_id}/frame", json={"time": 1.5}, headers=HEADERS).get_json()
    assert data["name"] == "screenshot.jpg" and data["data"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(data["data"].split(",", 1)[1])[:2] == b"\xff\xd8"
    assert client.post(f"/player/api/videos/{video_id}/frame", json={"time": "x"}, headers=HEADERS).status_code == 400
    assert client.post(f"/player/api/videos/{video_id}/frame", json={"time": 99}, headers=HEADERS).status_code == 400


@needs_ffmpeg
def test_audio_track_choice_prepares_again(client, library, tmp_path):
    video_id = upload(client, make_video(tmp_path / "neko.mp4")).get_json()["video"]["id"]
    res = client.post(f"/player/api/videos/{video_id}/prefs", json={"audio_track": 3}, headers=HEADERS)
    assert res.status_code == 400
    res = client.post(f"/player/api/videos/{video_id}/prepare", json={"level": "encode"}, headers=HEADERS)
    meta = res.get_json()["video"]
    assert meta["status"] == "ready" and meta["level"] == "encode" and meta["play_plan"]["video"] == "h264"
    assert (library / "videos" / video_id / "play.mp4").exists()
    # the level is kept when the video is prepared again (another audio track...)
    assert client.post(f"/player/api/videos/{video_id}/prepare", json={}, headers=HEADERS).get_json()["video"]["level"] == "encode"
    assert client.post(f"/player/api/videos/{video_id}/prepare", json={"level": "x"}, headers=HEADERS).status_code == 400


def test_broken_file_is_an_error(client, library):
    res = client.post("/player/api/videos?name=broken.mp4", data=b"not a video", headers=HEADERS)
    meta = res.get_json()["video"]
    assert meta["status"] == "error" and meta["error"]
    assert client.get(f"/player/api/videos/{meta['id']}/file").status_code == 400


def test_unsupported_upload(client):
    res = client.post("/player/api/videos?name=song.mp3", data=b"abc", headers=HEADERS)
    assert res.status_code == 400 and "Unsupported" in res.get_json()["error"]
    assert client.post("/player/api/videos?name=a.mp4", data=b"abc").status_code == 403  # no MiningCat header


def test_unknown_ids(client):
    assert client.get("/player/api/videos/../../etc").status_code == 404
    assert client.get("/player/api/videos/zzzz").status_code == 400
    assert client.get("/player/api/videos/0123456789abcdef").status_code == 400


def test_interrupted_preparation_restarts(library, monkeypatch):
    folder = library / "videos" / "0123456789abcdef"
    folder.mkdir(parents=True)
    (folder / "source.mp4").write_bytes(b"x")
    books._write_json(folder / "meta.json", {"id": "0123456789abcdef", "title": "t", "status": "preparing", "tracks": []})
    started = []
    monkeypatch.setattr(videos, "_spawn", lambda target, *args: started.append(args))
    videos.get_meta("0123456789abcdef")
    assert started == [("0123456789abcdef", None)]


# ---------------------------------------------------------------- progress, prefs, settings

def make_entry(library, video_id="0123456789abcdef", **meta):
    folder = library / "videos" / video_id
    folder.mkdir(parents=True)
    (folder / "source.mp4").write_bytes(b"x")
    books._write_json(folder / "meta.json", {"id": video_id, "title": "t", "status": "ready", "duration": 200,
                                             "tracks": [{"id": "1", "label": "ja"}], "audio": [{"index": 0, "codec": "aac"}], **meta})
    return video_id


def test_progress_and_prefs(client, library):
    video_id = make_entry(library)
    progress = client.post(f"/player/api/videos/{video_id}/progress", json={"time": 50}, headers=HEADERS).get_json()
    assert progress["time"] == 50 and progress["percent"] == 25
    assert client.post(f"/player/api/videos/{video_id}/progress", json={"time": "a"}, headers=HEADERS).status_code == 400

    prefs = client.post(f"/player/api/videos/{video_id}/prefs", json={"language": "ja", "primary": "1", "offset": 9999},
                        headers=HEADERS).get_json()
    assert prefs == {"language": "ja", "primary": "1", "offset": 600}
    assert client.post(f"/player/api/videos/{video_id}/prefs", json={"primary": "7"}, headers=HEADERS).status_code == 400
    assert client.post(f"/player/api/videos/{video_id}/prefs", json={"language": "<x>"}, headers=HEADERS).status_code == 400

    data = client.get(f"/player/api/videos/{video_id}").get_json()
    assert data["prefs"]["primary"] == "1" and data["progress"]["time"] == 50


def test_settings(client):
    assert client.get("/player/api/settings").get_json() == videos.DEFAULT_SETTINGS
    saved = client.post("/player/api/settings", json={"sub_size": 500, "sub_display": "blur", "auto_pause": 1,
                                                      "colors": "nope"}, headers=HEADERS).get_json()
    assert saved["sub_size"] == 80 and saved["sub_display"] == "blur" and saved["auto_pause"] is True
    assert saved["colors"] == "status"
    saved = client.post("/player/api/settings", json={"audio_before": -5, "audio_after": "350"}, headers=HEADERS).get_json()
    assert saved["audio_before"] == 0 and saved["audio_after"] == 350


def test_delete(client, library):
    video_id = make_entry(library)
    client.post(f"/player/api/videos/{video_id}/delete", headers=HEADERS)
    assert not (library / "videos" / video_id).exists()
    assert client.get("/player/api/videos").get_json()["videos"] == []


def test_pages(client):
    assert client.get("/player/").headers["Location"] == "/?next=/player/"
    client.post("/api/profile", json={"language": "ja"}, headers=HEADERS)
    assert client.get("/player/").status_code == 200
    assert b"player.js" in client.get("/player/0123456789abcdef").data


# ---------------------------------------------------------------- online videos & conversions

@needs_ffmpeg
def test_download(client, tmp_path, monkeypatch):
    import video_downloader

    (tmp_path / "videos").mkdir()
    downloaded = make_video(tmp_path / "videos" / "abc123.mp4")
    (tmp_path / "videos" / "abc123.ja.srt").write_text(JA_SRT, encoding="utf-8")
    calls = []

    def fake_download(url, output_dir, **options):
        calls.append((url, options.get("language")))
        return downloaded

    monkeypatch.setattr(video_downloader, "download_video", fake_download)
    monkeypatch.setattr(videos, "_online_title", lambda url: "吾輩は猫である")
    res = client.post("/player/api/videos/url", json={"url": "https://youtu.be/abc123", "language": "japanese"}, headers=HEADERS)
    job = res.get_json()["job"]
    assert calls[0][0] == "https://youtu.be/abc123" and calls[0][1].name == "JAPANESE"
    assert client.get("/player/api/videos").get_json()["downloads"] == []  # done

    video = client.get("/player/api/videos").get_json()["videos"][0]
    assert video["title"] == "吾輩は猫である" and video["tracks"] == 1
    data = client.get(f"/player/api/videos/{video['id']}").get_json()
    assert data["prefs"]["language"] == "ja-JP"
    assert data["video"]["tracks"][0]["origin"] == "platform" and data["video"]["tracks"][0]["label"] == "ja"
    assert job["status"] == "downloading"


def test_download_errors(client, monkeypatch):
    import video_downloader

    assert client.post("/player/api/videos/url", json={"url": "https://example.com/v"}, headers=HEADERS).status_code == 400
    assert client.post("/player/api/videos/url", json={"url": "https://youtu.be/x", "language": "klingon"},
                       headers=HEADERS).status_code == 400

    def failing(*args, **kwargs):
        raise RuntimeError("HTTP Error 403")

    monkeypatch.setattr(video_downloader, "download_video", failing)
    job = client.post("/player/api/videos/url", json={"url": "https://youtu.be/x"}, headers=HEADERS).get_json()["job"]
    pending = client.get("/player/api/videos").get_json()["downloads"]
    assert pending[0]["status"] == "error" and "403" in pending[0]["error"]
    client.post(f"/player/api/downloads/{job['id']}/dismiss", headers=HEADERS)
    assert client.get("/player/api/videos").get_json()["downloads"] == []


@needs_ffmpeg
def test_from_output(client, tmp_path, monkeypatch):
    import config

    final = tmp_path / "output" / "final"
    final.mkdir(parents=True)
    monkeypatch.setattr(config, "DIR_FINAL", final)
    assert client.post("/api/player/from-output", json={}, headers=HEADERS).status_code == 400
    make_video(final / "movie.mp4")
    res = client.post("/api/player/from-output", json={"language": "mandarin_tw"}, headers=HEADERS)
    video_id = res.get_json()["id"]
    assert videos.get_prefs(video_id)["language"] == "zh-Hant"
    # hard-linked: the converted video isn't copied
    source = tmp_path / "library" / "videos" / video_id / "source.mp4"
    assert source.stat().st_ino == (final / "movie.mp4").stat().st_ino
