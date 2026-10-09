import io
import threading

import pytest

pytest.importorskip("flask")

from miningcat.application.converter.errors import ConverterError
from miningcat.application.converter.jobs import Job
from miningcat.domain.languages import Language
from miningcat.domain.ocr.sampling import OCR_FPS_MAX
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web import jobs as web_jobs
from miningcat.interfaces.web.blueprints import converter, converter_files, converter_results
from miningcat.interfaces.web.event_bus import EventBus
from miningcat.interfaces.web.jobs import AppState, JobBusyError

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def project(tmp_path):
    """The project's root (conftest points every path there)."""
    return tmp_path


@pytest.fixture
def state():
    return AppState()


@pytest.fixture
def client(project, state):
    app = web_app.create_app(state)
    app.testing = True
    return app.test_client()


def post(client, url, json=None, **kwargs):
    return client.post(url, json=json if json is not None else {}, headers=HEADERS, **kwargs)


def upload(client, kind, *named_contents):
    data = {"files": [(io.BytesIO(content), name) for name, content in named_contents]}
    return client.post(f"/api/upload/{kind}", data=data, headers=HEADERS, content_type="multipart/form-data")


class FakeThread:
    """Runs the job synchronously so that tests can inspect the events right away."""

    def __init__(self, target, daemon=None, name=None):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def sync_jobs(monkeypatch):
    monkeypatch.setattr(web_jobs.threading, "Thread", FakeThread)


def events(state: AppState) -> list[dict]:
    return [e for _, e in state.bus.events_after(0)]


class FakeJob(Job):
    """Stands for the jobs of the converter: keeps its request, logs a line, and returns `result`."""

    kind = "fake"
    received = []

    def __init__(self, request, result=None, release: threading.Event | None = None):
        self.request, self.result, self.release = request, result, release
        FakeJob.received.append(request)

    def run(self, listener):
        if self.release is not None:
            self.release.wait(5)
        listener.log("hello\n")
        listener.status("Done", 100)
        return self.result


@pytest.fixture
def fake_jobs(monkeypatch):
    FakeJob.received = []
    monkeypatch.setattr(converter, "AudiobookJob", lambda request: FakeJob(request))
    monkeypatch.setattr(converter, "VideoJob", lambda request: FakeJob(request))
    return FakeJob.received


def test_options_endpoint(client):
    data = client.get("/api/options").get_json()
    ids = [lang["id"] for lang in data["languages"]]
    assert ids == Language.ids()
    tw = next(lang for lang in data["languages"] if lang["id"] == "mandarin_tw")
    assert tw["char_list"] is True
    assert tw["default_voice"].startswith("HsiaoChen")
    assert data["ocr"]["fps_min"] <= data["ocr"]["fps_default"] <= data["ocr"]["fps_max"]
    assert data["websites"] == ["Instagram", "YouTube", "Bilibili"]


# local-only guard

def test_post_without_header_is_refused(client):
    assert client.post("/api/clear-output", json={}).status_code == 403


def test_non_local_host_is_refused(client):
    res = client.get("/api/options", headers={"Host": "evil.example.com"})
    assert res.status_code == 403


def test_index_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"MiningCat" in res.data


def test_clipboard_page(client):
    assert client.get("/clipboard/").headers["Location"] == "/?next=/clipboard/"
    post(client, "/api/profile", {"language": "zh"})
    res = client.get("/clipboard/")
    assert res.status_code == 200
    assert b"clipboard.js" in res.data and b"zh-Hant" in res.data
    assert b'href="/clipboard/"' in client.get("/").data


# files

def test_upload_then_discard_audio(client, project):
    res = upload(client, "audio", ("ch01.mp3", b"abc"), ("notes.pdf", b"x"))
    data = res.get_json()
    assert data["files"] == [{"path": "sources/.staging/audio/ch01.mp3", "name": "ch01.mp3"}]
    assert data["rejected"] == ["notes.pdf"]
    staged = project / "sources/.staging/audio/ch01.mp3"
    assert staged.read_bytes() == b"abc"

    assert post(client, "/api/discard", {"path": "sources/.staging/audio/ch01.mp3"}).get_json() == {"removed": True}
    assert not staged.exists()


def test_upload_keeps_unicode_names(client):
    data = upload(client, "ebook", ("第一章.txt", "內容".encode())).get_json()
    assert data["files"][0]["name"] == "第一章.txt"


def test_discard_never_deletes_source_files(client, project):
    kept = project / "sources/audiobook/book.mp3"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"x")
    assert post(client, "/api/discard", {"path": "sources/audiobook/book.mp3"}).get_json() == {"removed": False}
    assert kept.exists()


def test_paths_outside_sources_are_refused(client, project):
    (project / "secret.txt").write_text("x")
    res = post(client, "/api/chapters", {"files": ["sources/../secret.txt"]})
    assert res.status_code == 400
    assert "outside" in res.get_json()["error"]


def test_state_preloads_source_files(client, project):
    (project / "sources/audiobook").mkdir(parents=True)
    (project / "sources/audiobook/01.mp3").write_bytes(b"x")
    (project / "sources/ebook").mkdir(parents=True)
    (project / "sources/ebook/b.txt").write_text("x")
    data = client.get("/api/state").get_json()
    assert [f["name"] for f in data["files"]["audio"]] == ["01.mp3"]
    assert [f["name"] for f in data["files"]["ebook"]] == ["b.txt"]
    assert data["job"]["running"] is False


def test_chapters_from_several_txt_files(client):
    upload(client, "ebook", ("b.txt", "第二章 內容".encode()), ("a.txt", "第一章 內容".encode()))
    res = post(client, "/api/chapters", {"files": ["sources/.staging/ebook/b.txt", "sources/.staging/ebook/a.txt"]})
    data = res.get_json()
    assert [c["title"] for c in data["chapters"]] == ["a", "b"]
    assert data["error"] is None


# audiobook conversions

def test_audiobook_requires_audio(client):
    res = post(client, "/api/run/audiobook", {"mode": "Standard", "language": "mandarin_tw", "audio": [], "ebook": []})
    assert res.status_code == 400
    assert res.get_json()["title"] == "Missing files"


def test_audiobook_requires_a_known_mode(client):
    res = post(client, "/api/run/audiobook", {"mode": "Karaoke", "language": "mandarin_tw"})
    assert res.get_json()["title"] == "Unknown mode"


def test_audiobook_requires_a_selected_chapter(client):
    upload(client, "audio", ("01.mp3", b"x"))
    upload(client, "ebook", ("a.txt", "內容".encode()))
    res = post(client, "/api/run/audiobook", {
        "mode": "Standard", "language": "mandarin_tw",
        "audio": ["sources/.staging/audio/01.mp3"], "ebook": ["sources/.staging/ebook/a.txt"], "chapters": [],
    })
    assert res.status_code == 400
    assert res.get_json()["title"] == "No chapters selected"


def test_audiobook_runs_a_job(client, state, sync_jobs, fake_jobs):
    upload(client, "audio", ("01.mp3", b"x"))
    upload(client, "ebook", ("a.txt", "一".encode()), ("b.txt", "二".encode()))
    res = post(client, "/api/run/audiobook", {
        "mode": "Standard", "language": "mandarin_tw",
        "convert": "Simplified - China", "precision": "Small (oops, not a value)",
        "audio": ["sources/.staging/audio/01.mp3"],
        "ebook": ["sources/.staging/ebook/a.txt", "sources/.staging/ebook/b.txt"],
        "chapters": [1, 7, "x"],
    })
    assert res.status_code == 200
    request = fake_jobs[0]
    assert request.mode.value == "Standard"
    assert request.language is Language.MANDARIN_TW
    assert request.model_name == "base"  # unknown precision falls back to the default
    assert request.convert_target == "s"
    assert request.selected_chapters == [1] and request.total_chapters == 2
    assert [p.name for p in request.audio_files] == ["01.mp3"]

    types = [e["type"] for e in events(state)]
    assert types == ["start", "status", "log", "status", "done", "finish"]
    assert state.running is False


def test_generate_audio_needs_a_voice_but_no_audio(client, sync_jobs, fake_jobs):
    upload(client, "ebook", ("a.txt", "一".encode()))
    body = {"mode": "Generate audio", "language": "mandarin_tw", "ebook": ["sources/.staging/ebook/a.txt"], "chapters": [0]}
    assert post(client, "/api/run/audiobook", {**body, "voice": "nope"}).status_code == 400
    assert post(client, "/api/run/audiobook", {**body, "voice": "YunJhe - Mandarin (Taiwan), male"}).status_code == 200
    assert fake_jobs[0].voice_id == "zh-TW-YunJheNeural"
    assert fake_jobs[0].audio_files == []


def test_only_one_job_at_a_time(client, state, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(converter, "VideoJob", lambda request: FakeJob(request, release=release))
    body = {"input_mode": "From web", "website": "YouTube", "url": "https://youtu.be/x", "language": "japanese"}
    try:
        assert post(client, "/api/run/video", body).status_code == 200
        assert state.running
        assert post(client, "/api/run/video", body).status_code == 409
        assert post(client, "/api/clear-output").status_code == 409
    finally:
        release.set()


def test_failed_job_is_reported(client, state, sync_jobs, monkeypatch):
    class Failing(FakeJob):
        def run(self, listener):
            raise ConverterError("boom")

    monkeypatch.setattr(converter, "VideoJob", lambda request: Failing(request))
    post(client, "/api/run/video", {"input_mode": "From web", "website": "YouTube", "url": "https://youtu.be/x",
                                    "language": "japanese"})
    logged = [e for e in events(state) if e["type"] == "log"]
    assert logged[-1]["text"] == "\n[ERROR] boom\n"
    assert not any(e["type"] == "done" for e in events(state))


# video conversions

def test_video_requires_url(client):
    res = post(client, "/api/run/video", {"input_mode": "From web", "url": "", "language": "japanese"})
    assert res.get_json()["title"] == "Missing URL"


def test_video_rejects_mismatched_url(client):
    res = post(client, "/api/run/video", {"input_mode": "From web", "website": "Bilibili", "url": "https://youtu.be/x",
                                          "language": "japanese"})
    assert res.status_code == 400
    assert res.get_json()["title"] == "URL mismatch"


def test_local_video_with_ocr(client, state, sync_jobs, monkeypatch, project):
    srt = project / "output/srt/movie_ocr.srt"
    received = []
    monkeypatch.setattr(converter, "VideoJob", lambda request: received.append(request) or FakeJob(request, srt))
    upload(client, "video", ("movie.mkv", b"x"))
    res = post(client, "/api/run/video", {
        "input_mode": "Local file", "path": "sources/.staging/video/movie.mkv", "language": "mandarin_cn",
        "audio_track": 2, "ocr": True, "ocr_region": [0, 0.5, 1, 0.5], "ocr_fps": 99,
    })
    assert res.status_code == 200
    request = received[0]
    assert request.video_path.name == "movie.mkv" and request.url is None
    assert request.audio_track == 2
    assert request.ocr_region == (0.0, 0.5, 1.0, 0.5)
    assert request.ocr_fps == OCR_FPS_MAX
    assert state.last_video_srt == srt
    assert {"type": "done", "kind": "video", "has_srt": True} in events(state)


def test_invalid_ocr_region_is_refused(client):
    upload(client, "video", ("movie.mp4", b"x"))
    res = post(client, "/api/run/video", {
        "input_mode": "Local file", "path": "sources/.staging/video/movie.mp4", "language": "japanese",
        "ocr": True, "ocr_region": [0, 0, 2, 1],
    })
    assert res.status_code == 400
    assert res.get_json()["title"] == "Invalid region"


# frequency lists & output

def test_character_list_from_selected_chapters(client, project):
    upload(client, "ebook", ("a.txt", "天天".encode()), ("b.txt", "地".encode()))
    res = post(client, "/api/frequency", {
        "kind": "char", "source": "book", "language": "mandarin_tw",
        "ebook": ["sources/.staging/ebook/a.txt", "sources/.staging/ebook/b.txt"], "chapters": [0],
    })
    assert res.status_code == 200, res.get_json()
    assert "1 unique characters" in res.get_json()["message"]
    assert (project / "output/frequency/a_char_list.json").exists()


def test_character_list_not_offered_for_french(client):
    res = post(client, "/api/frequency", {"kind": "char", "source": "video", "language": "french"})
    assert res.status_code == 400


def test_video_frequency_needs_a_generated_video(client):
    res = post(client, "/api/frequency", {"kind": "word", "source": "video", "language": "french"})
    assert res.get_json()["title"] == "No video processed"


def test_word_frequency_from_last_video(client, state, project):
    srt = project / "output/srt/clip_whisper.srt"
    srt.parent.mkdir(parents=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour le monde, bonjour !\n", encoding="utf-8")
    state.last_video_srt = srt
    res = post(client, "/api/frequency", {"kind": "word", "source": "video", "language": "french"})
    assert res.status_code == 200, res.get_json()
    assert (project / "output/frequency/clip_whisper_word_freq.csv").exists()


def test_clear_output(client, state, project):
    (project / "output/final").mkdir(parents=True)
    (project / "output/final/a.mp4").write_bytes(b"x")
    state.last_video_srt = project / "output/srt/x.srt"
    assert post(client, "/api/clear-output").status_code == 200
    assert list((project / "output").iterdir()) == []
    assert state.last_video_srt is None
    assert events(state)[-1] == {"type": "log", "text": "Output folder cleared.\n"}


# event bus and jobs

def test_event_bus_reset_keeps_ids_increasing():
    bus = EventBus()
    first = bus.publish({"n": 1})
    bus.reset()
    second = bus.publish({"n": 2})
    assert second > first
    assert bus.events_after(0) == [(second, {"n": 2})]
    assert bus.last_id == second


def test_event_bus_follow_streams_new_events():
    bus = EventBus()
    bus.publish({"n": 1})
    stream = bus.follow(0, keepalive=0.01)
    assert next(stream) == (1, {"n": 1})
    assert next(stream) is None  # keep-alive while idle
    bus.publish({"n": 2})
    assert next(stream) == (2, {"n": 2})


def test_events_endpoint_replays_the_current_job(client, state):
    state.bus.publish({"type": "log", "text": "hi"})
    state.bus.close()  # lets the stream end after the replay
    body = client.get("/api/events").get_data(as_text=True)
    assert 'data: {"type": "log", "text": "hi"}' in body
    assert "id: 1" in body


def test_start_job_refuses_a_second_job():
    state = AppState()
    release = threading.Event()
    state.start_job(FakeJob(None, release=release))
    try:
        with pytest.raises(JobBusyError):
            state.start_job(FakeJob(None))
    finally:
        release.set()


# video helpers & folders

def test_audio_tracks_are_labelled(client, monkeypatch):
    monkeypatch.setattr(converter_files, "list_audio_tracks", lambda path: [
        {"index": 0, "language": "jpn", "title": "", "channels": 2},
        {"index": 1, "language": "chi", "title": "Mandarin (Taiwan)", "channels": 1},
    ])
    upload(client, "video", ("movie.mkv", b"x"))
    data = post(client, "/api/video/tracks", {"path": "sources/.staging/video/movie.mkv"}).get_json()
    assert data["tracks"] == [
        {"index": 0, "label": "Track 0 - jpn - stereo"},
        {"index": 1, "label": "Track 1 - Mandarin (Taiwan) - mono"},
    ]


def test_ocr_preview_serves_frames(client, monkeypatch):
    def fake_grab(video_file, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        frames = [output_dir / f"preview_{i:02d}.jpg" for i in range(2)]
        for p in frames:
            p.write_bytes(b"\xff\xd8jpeg")
        return frames

    monkeypatch.setattr(converter_files.video_frames, "grab_sample_frames", fake_grab)
    monkeypatch.setattr(converter_files.video_frames, "probe_dimensions", lambda video_file: (1280, 720))
    upload(client, "video", ("movie.mp4", b"x"))
    data = post(client, "/api/ocr/preview", {"path": "sources/.staging/video/movie.mp4"}).get_json()
    assert (data["width"], data["height"]) == (1280, 720)
    assert len(data["frames"]) == 2
    assert client.get(data["frames"][1]).data == b"\xff\xd8jpeg"
    assert client.get("/api/ocr/frame/9").status_code == 404


def test_ocr_preview_reports_download_errors(client, monkeypatch):
    def boom(url, output_dir, **kwargs):
        raise RuntimeError("private video")

    monkeypatch.setattr(converter_files, "download_video", boom)
    res = post(client, "/api/ocr/preview", {"url": "https://youtu.be/x"})
    assert res.status_code == 400
    assert res.get_json()["title"] == "Download failed"


def test_open_folder(client, monkeypatch, project):
    opened = []
    monkeypatch.setattr(converter_results, "open_folder", opened.append)
    assert post(client, "/api/open-folder", {"which": "frequency"}).status_code == 200
    assert opened == [project / "output/frequency"]
