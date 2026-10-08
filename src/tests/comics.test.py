import io
import shutil
import sys
import zipfile

import pytest

pytest.importorskip("flask")
from PIL import Image

from ocr_mining import layout
from web import app as web_app
from web import books, comics
from web.state import AppState

HEADERS = {"X-MiningCat": "1"}


# ---------------------------------------------------------------- grouping lines into blocks

def test_vertical_columns_of_a_bubble_are_one_block_read_right_to_left():
    # two bubbles of two columns each (as Apple Live Text reads them), and a horizontal caption
    lines = [
        layout.Line("名前はまだ無い", 600, 80, 36, 276),
        layout.Line("吾輩は猫である", 650, 82, 36, 276),
        layout.Line("どこで生れたか", 200, 500, 38, 276),
        layout.Line("とんと見当がつかぬ", 150, 500, 38, 354),
        layout.Line("何でも薄暗いじめじめした所で", 78, 950, 506, 46),
    ]
    blocks = layout.group_lines(lines, right_to_left=True)
    assert [layout.block_text(b, no_space=True) for b in blocks] == [
        "吾輩は猫である名前はまだ無い", "どこで生れたかとんと見当がつかぬ", "何でも薄暗いじめじめした所で"]
    assert [b.vertical for b in blocks] == [True, True, False]


def test_horizontal_lines_of_a_bubble_are_one_block_read_top_to_bottom():
    lines = [
        layout.Line("you doing here?", 105, 160, 150, 22),
        layout.Line("What are", 120, 130, 90, 22),
        layout.Line("Far away", 600, 130, 90, 22),  # another bubble, beside it
    ]
    blocks = layout.group_lines(lines, right_to_left=False)
    assert [layout.block_text(b, no_space=False) for b in blocks] == ["What are you doing here?", "Far away"]


def test_lines_of_very_different_sizes_stay_apart():
    # a big sound effect next to a small dialogue column
    lines = [layout.Line("ドン", 300, 100, 120, 260), layout.Line("なに", 260, 100, 30, 70)]
    assert len(layout.group_lines(lines)) == 2


def test_single_characters_join_the_column_next_to_them():
    lines = [layout.Line("え", 500, 100, 30, 30), layout.Line("本当に", 460, 100, 30, 92)]
    blocks = layout.group_lines(lines)
    assert len(blocks) == 1 and blocks[0].vertical
    assert layout.block_text(blocks[0], no_space=True) == "え本当に"


def test_blocks_as_json_are_fractions_of_the_page():
    blocks = layout.group_lines([layout.Line("猫", 100, 50, 20, 40)])
    data = layout.to_json(blocks, 200, 100, no_space=True)
    assert data == [{"box": [0.5, 0.5, 0.1, 0.4], "vertical": True, "text": "猫",
                     "lines": [{"text": "猫", "box": [0.5, 0.5, 0.1, 0.4]}]}]


# ---------------------------------------------------------------- library

def page_bytes(color, size=(60, 90), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def make_cbz(path, names):
    with zipfile.ZipFile(path, "w") as zf:
        for i, name in enumerate(names):
            zf.writestr(name, page_bytes((i * 20, 0, 0), fmt="JPEG" if name.endswith(".jpg") else "PNG"))
        zf.writestr("info.txt", "not a page")
        zf.writestr("__MACOSX/._page1.png", "resource fork")
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "DIR_LIBRARY", tmp_path / "library")
    return tmp_path / "library"


@pytest.fixture
def client(library, tmp_path, monkeypatch):
    from web import files
    monkeypatch.setattr(files, "ROOT", tmp_path)
    app = web_app.create_app(AppState())
    app.testing = True
    client = app.test_client()
    client.post("/api/profile", json={"language": "ja"}, headers=HEADERS)
    return client


def test_import_sorts_pages_naturally_and_skips_other_files(library, tmp_path):
    archive = make_cbz(tmp_path / "Neko vol 1.cbz", ["ch1/page10.png", "ch1/page2.jpg", "ch1/page1.png", "ch2/page1.png"])
    meta = comics.import_file(archive, title="Neko vol 1")
    assert [p["file"] for p in meta["pages"]] == ["0001.png", "0002.jpg", "0003.png", "0004.png"]
    assert meta["pages"][0] == {"file": "0001.png", "width": 60, "height": 90}
    folder = comics.comics_dir() / meta["id"]
    # page2 (red 20) comes before page10 (red 0... the first written)
    with Image.open(folder / "pages" / "0002.jpg") as img:
        assert abs(img.getpixel((30, 45))[0] - 20) < 8
    assert (folder / "thumb.jpg").is_file()
    # the same archive again: the same comic
    assert comics.import_file(archive)["id"] == meta["id"]


def test_import_never_writes_outside_the_comic(library, tmp_path):
    archive = tmp_path / "evil.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escaped.png", page_bytes("red"))
        zf.writestr("/abs/page.png", page_bytes("blue"))
    meta = comics.import_file(archive)
    assert len(meta["pages"]) == 1  # the absolute path lands inside; the one going up is skipped
    assert not (tmp_path / "escaped.png").exists() and not (library / "escaped.png").exists()


def test_import_rejects_archives_without_pages(library, tmp_path):
    archive = tmp_path / "empty.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(comics.ComicError, match="No images"):
        comics.import_file(archive)
    assert not any(comics.comics_dir().glob("*/meta.json"))


@pytest.mark.skipif(shutil.which("bsdtar") is None, reason="bsdtar isn't installed")
def test_import_tar_archives_with_bsdtar(library, tmp_path):
    import tarfile
    archive = tmp_path / "book.cbt"
    with tarfile.open(archive, "w") as tf:
        for i in (1, 2):
            data = page_bytes("green")
            info = tarfile.TarInfo(f"p{i}.png")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    assert len(comics.import_file(archive)["pages"]) == 2


def test_ocr_language_follows_the_script():
    from miningcat.domain.languages import Language
    assert comics.ocr_language("ja") is Language.JAPANESE
    assert comics.ocr_language("zh-Hant") is Language.MANDARIN_TW
    assert comics.ocr_language("zh-Hans") is Language.MANDARIN_CN
    assert comics.ocr_language("yue-Hant") is Language.CANTONESE_HK
    with pytest.raises(comics.ComicError):
        comics.ocr_language("ru")


# ---------------------------------------------------------------- web API

class FakeWorker:
    def __init__(self):
        self.calls = []

    def read(self, language, image):
        self.calls.append((language.name, image.name))
        return {"width": 60, "height": 90, "lines": [
            ["吾輩は猫である", 40, 5, 6, 40], ["名前はまだ無い", 32, 5, 6, 40], ["!!", 2, 80, 10, 5]]}


def test_api_import_read_and_text(client, tmp_path, monkeypatch):
    worker = FakeWorker()
    monkeypatch.setattr(comics, "_worker", worker)
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png", "2.png"])
    res = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS)
    assert res.status_code == 200, res.json
    comic_id = res.json["comic"]["id"]

    listing = client.get("/reader/api/comics").json
    assert [c["id"] for c in listing["comics"]] == [comic_id] and listing["comics"][0]["language"] == "ja"
    assert client.get(f"/reader/comic/{comic_id}").status_code == 200
    assert client.get(f"/reader/api/comics/{comic_id}/pages/2").status_code == 200
    assert client.get(f"/reader/api/comics/{comic_id}/pages/3").status_code == 400

    text = client.get(f"/reader/api/comics/{comic_id}/pages/1/text").json
    # the two columns are one bubble, read right to left (Japanese); the noise without Japanese is dropped
    assert [b["text"] for b in text["blocks"]] == ["吾輩は猫である名前はまだ無い"]
    # read once, then from the cache…
    client.get(f"/reader/api/comics/{comic_id}/pages/1/text")
    assert worker.calls == [("JAPANESE", "0001.png")]
    # …unless asked again, or read in another script
    client.get(f"/reader/api/comics/{comic_id}/pages/1/text?again=1")
    client.post(f"/reader/api/comics/{comic_id}/prefs", json={"direction": "ltr"}, headers=HEADERS)
    text = client.get(f"/reader/api/comics/{comic_id}/pages/1/text").json
    assert text["blocks"][0]["text"] == "名前はまだ無い吾輩は猫である"  # left to right now
    assert len(worker.calls) == 2

    assert client.post(f"/reader/api/comics/{comic_id}/progress", json={"page": 2}, headers=HEADERS).json["percent"] == 100
    assert client.get(f"/reader/api/comics/{comic_id}").json["progress"]["page"] == 2

    assert client.post(f"/reader/api/comics/{comic_id}/delete", json={}, headers=HEADERS).json["deleted"]
    assert client.get("/reader/api/comics").json["comics"] == []


def test_api_rejects_unknown_formats_and_ids(client):
    res = client.post("/reader/api/comics?name=book.pdf", data=b"%PDF", headers=HEADERS)
    assert res.status_code == 400 and "Unsupported format" in res.json["error"]
    assert client.get("/reader/api/comics/../../etc").status_code == 404
    assert client.get("/reader/api/comics/0123456789abcdef").status_code == 400


def test_comic_settings_are_validated(client):
    assert client.get("/reader/api/comic-settings").json["text"] == "hover"
    saved = client.post("/reader/api/comic-settings", json={"text": "always", "spread": "nope", "first_single": False},
                        headers=HEADERS).json
    assert saved["text"] == "always" and saved["spread"] == "auto" and saved["first_single"] is False


# ---------------------------------------------------------------- the real OCR (macOS)

@pytest.mark.skipif(sys.platform != "darwin", reason="Apple Live Text is macOS only")
def test_worker_reads_vertical_japanese(tmp_path):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", 36)
    except OSError:
        pytest.skip("Hiragino isn't installed")
    img = Image.new("RGB", (400, 500), "white")
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate("吾輩は猫である"):
        draw.text((300, 60 + i * 40), ch, font=font, fill="black")
    img.save(tmp_path / "page.png")
    worker = comics._OcrWorker()
    try:
        from miningcat.domain.languages import Language
        result = worker.read(Language.JAPANESE, tmp_path / "page.png")
    except comics.ComicError as exc:
        pytest.skip(f"OCR unavailable: {exc}")
    finally:
        worker._stop()
    assert any("猫" in line[0] for line in result["lines"])
