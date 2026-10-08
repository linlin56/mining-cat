import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest
from PIL import Image

from miningcat.interfaces.cli import area_picker


def get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def answer(url: str, body: dict) -> int:
    request = urllib.request.Request(url + "answer", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def run(picker: area_picker.AreaPicker, user) -> object:
    """Waits for the picker's answer while `user(url)` plays the browser in another thread."""
    threading.Thread(target=user, args=(picker.url,), daemon=True).start()
    return picker.wait()


@pytest.fixture
def picker():
    return area_picker.AreaPicker(Image.new("RGB", (160, 90), "white"), "Pick <the area>",
                                  default_region=(0, 0.5, 1, 0.5), initial_region=(0.1, 0.1, 0.2, 0.2))


def test_the_page_shows_the_capture_and_the_regions(picker):
    def user(url):
        status, page = get(url)
        assert status == 200
        assert b"Pick &lt;the area&gt;" in page
        assert b"const defaultRegion = [0, 0.5, 1, 0.5];" in page
        assert b"let region = [0.1, 0.1, 0.2, 0.2];" in page
        status, jpeg = get(url + "frame.jpg")
        assert status == 200 and jpeg.startswith(b"\xff\xd8")
        answer(url, {"cancel": True})

    assert run(picker, user) is None


def test_ok_returns_the_drawn_region(picker):
    assert run(picker, lambda url: answer(url, {"region": [0, 0.5, 0.5, 0.5]})) == (0.0, 0.5, 0.5, 0.5)


def test_invalid_regions_are_refused_until_a_valid_answer(picker):
    statuses = []

    def user(url):
        statuses.append(answer(url, {"region": [0, 0, 2, 1]}))
        statuses.append(answer(url, {"region": "nope"}))
        statuses.append(answer(url, {"region": [0, 0, 1, 1]}))

    assert run(picker, user) == (0.0, 0.0, 1.0, 1.0)
    assert statuses == [400, 400, 204]


def test_only_the_page_with_the_token_answers(picker):
    def user(url):
        root = url.rsplit("/", 2)[0] + "/"
        assert get(root)[0] == 404
        assert answer(root + "wrong-token/", {"cancel": True}) == 404
        answer(url, {"region": [0, 0, 1, 1]})

    assert run(picker, user) == (0.0, 0.0, 1.0, 1.0)


def test_pick_region_opens_the_page_in_the_browser():
    with patch.object(area_picker.webbrowser, "open",
                      side_effect=lambda url: threading.Thread(target=answer, args=(url, {"cancel": True})).start()) as opened:
        assert area_picker.pick_region(Image.new("RGB", (80, 45)), "Pick") is None
    assert opened.call_args[0][0].startswith("http://127.0.0.1:")
