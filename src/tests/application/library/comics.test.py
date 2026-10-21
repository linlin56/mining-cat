import io
import shutil
import sys
import zipfile

import pytest

from miningcat.infrastructure.ocr.worker_client import OcrWorker

pytest.importorskip("flask")
from PIL import Image

from miningcat.application.library import books, comics
from miningcat.application.library.comics import ocr as page_text
from miningcat.domain.ocr import layout
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

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
    return tmp_path / "library"


@pytest.fixture(autouse=True)
def background_reading_at_once(monkeypatch):
    """The background OCR doesn't wait after the pages the tests read, and forgets what it couldn't read."""
    monkeypatch.setattr(page_text, "READER_PAUSE", 0)
    monkeypatch.setattr(page_text, "_unavailable", {})
    monkeypatch.setattr(page_text, "_retried", set())
    monkeypatch.setattr(page_text, "_states", {})


@pytest.fixture
def client(library, tmp_path, monkeypatch):
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
    assert meta["new"]
    # the same archive again: the same comic
    again = comics.import_file(archive)
    assert again["id"] == meta["id"] and not again["new"]


def test_import_never_writes_outside_the_comic(library, tmp_path):
    archive = tmp_path / "evil.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escaped.png", page_bytes("red"))
        zf.writestr("/abs/page.png", page_bytes("blue"))
    meta = comics.import_file(archive)
    assert len(meta["pages"]) == 1  # the absolute path lands inside; the one going up is skipped
    assert not (tmp_path / "escaped.png").exists() and not (library / "escaped.png").exists()


def test_import_a_single_image_as_a_comic_of_one_page(library, tmp_path):
    picture = tmp_path / "Sign.webp"
    picture.write_bytes(page_bytes("blue", fmt="WEBP"))
    meta = comics.import_file(picture, title="Sign")
    assert meta["image"] and meta["pages"] == [{"file": "0001.webp", "width": 60, "height": 90}]
    assert picture.exists()  # copied, not moved
    assert (comics.comics_dir() / meta["id"] / "thumb.jpg").is_file()
    assert comics.list_comics()[0]["image"]


def test_import_converts_images_browsers_dont_show(library, tmp_path):
    picture = tmp_path / "scan.bmp"
    picture.write_bytes(page_bytes("blue", fmt="BMP"))
    assert comics.import_file(picture)["pages"][0]["file"] == "0001.png"


def test_import_rejects_a_damaged_image(library, tmp_path):
    picture = tmp_path / "broken.png"
    picture.write_bytes(b"not a picture")
    with pytest.raises(comics.ComicError, match="isn't an image"):
        comics.import_file(picture)
    assert not any(comics.comics_dir().glob("*/meta.json"))


def test_import_rejects_archives_without_pages(library, tmp_path):
    archive = tmp_path / "empty.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(comics.ComicError, match="No images"):
        comics.import_file(archive)
    assert not any(comics.comics_dir().glob("*/meta.json"))


def make_pdf(path, colors, size=(60, 90)):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    for color in colors:
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_image(page.rect, stream=page_bytes(color, size=(size[0] * 4, size[1] * 4)))
    doc.save(path)
    return path


def test_import_a_pdf_renders_its_pages_at_the_resolution_of_its_scans(library, tmp_path):
    pdf = make_pdf(tmp_path / "Scan vol 1.pdf", [(200, 0, 0), (0, 0, 200)])
    meta = comics.import_file(pdf, title="Scan vol 1")
    assert [p["file"] for p in meta["pages"]] == ["0001.jpg", "0002.jpg"]
    assert (meta["pages"][0]["width"], meta["pages"][0]["height"]) == (240, 360)  # the scans' 4x, not the 72 dpi page
    with Image.open(comics.comics_dir() / meta["id"] / "pages" / "0002.jpg") as img:
        assert img.getpixel((120, 180))[2] > 180
    assert (comics.comics_dir() / meta["id"] / "thumb.jpg").is_file()
    assert not meta["image"]


def test_import_rejects_a_damaged_pdf(library, tmp_path):
    pytest.importorskip("pymupdf")
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")
    with pytest.raises(comics.ComicError, match="damaged"):
        comics.import_file(pdf)
    assert not any(comics.comics_dir().glob("*/meta.json"))


def test_import_rejects_a_pdf_with_a_password(library, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = make_pdf(tmp_path / "plain.pdf", ["red"])
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(pdf) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="neko", owner_pw="neko")
    with pytest.raises(comics.ComicError, match="password"):
        comics.import_file(locked)


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
    assert comics.ocr_language("ru") is Language.RUSSIAN
    with pytest.raises(comics.ComicError):
        comics.ocr_language("ar")


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
    monkeypatch.setattr(page_text, "_worker", worker)
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


def test_api_comprehension_reads_the_other_pages_in_the_background(client, tmp_path, monkeypatch):
    import threading
    worker = FakeWorker()
    monkeypatch.setattr(page_text, "_worker", worker)
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png", "2.png"])
    comic_id = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS).json["comic"]["id"]

    client.get(f"/reader/api/comics/{comic_id}/pages/1/text")
    first = client.get(f"/reader/api/comics/{comic_id}/comprehension").json
    # not every page read: nothing yet (it would change as the pages are read)
    assert first["read"] == 1 and first["pages"] == 2 and first["comprehension"] is None
    for thread in threading.enumerate():
        if thread.name == "ocr-background":
            thread.join(5)
    assert sorted(name for _, name in worker.calls) == ["0001.png", "0002.png"]

    done = client.get(f"/reader/api/comics/{comic_id}/comprehension").json
    assert done["read"] == 2 and done["comprehension"] is not None
    assert (comics.comics_dir() / comic_id / "comprehension.json").is_file()
    assert len(worker.calls) == 2  # every page read: nothing more to read


def test_api_a_pdf_with_text_gives_its_text_without_ocr(client, tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    worker = FakeWorker()
    monkeypatch.setattr(page_text, "_worker", worker)
    pdf = tmp_path / "manuel.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((20, 50), "吾輩は猫である。", fontname="japan", fontsize=14)
    page.insert_text((20, 70), "名前はまだ無い。", fontname="japan", fontsize=14)
    doc.new_page(width=300, height=400)  # a page without text: read by OCR
    doc.save(pdf)
    comic_id = client.post("/reader/api/comics?name=manuel.pdf", data=pdf.read_bytes(), headers=HEADERS).json["comic"]["id"]
    assert client.get("/reader/api/comics").json["comics"][0]["pdf"]  # shown as a document

    text = client.get(f"/reader/api/comics/{comic_id}/pages/1/text").json
    assert [b["text"] for b in text["blocks"]] == ["吾輩は猫である。名前はまだ無い。"]
    box = text["blocks"][0]["box"]
    assert 0 < box[0] < 0.2 and 0.05 < box[1] < 0.2  # where the text is on the page
    assert worker.calls == []  # never read by OCR…
    assert client.get(f"/reader/api/comics/{comic_id}/comprehension").json["read"] == 2  # (the blank page has no text)
    assert worker.calls == []
    # …unless asked to read it again: what the OCR read is then the page's text
    again = client.get(f"/reader/api/comics/{comic_id}/pages/1/text?again=1").json
    assert worker.calls == [("JAPANESE", "0001.jpg")] and again["blocks"][0]["text"] == "吾輩は猫である名前はまだ無い"


def wait_for_background_reading():
    import threading
    for thread in threading.enumerate():
        if thread.name == "ocr-background":
            thread.join(5)


class FailingWorker(FakeWorker):
    """Can't read page 1, reads the others."""

    def read(self, language, image):
        from miningcat.infrastructure.ocr.worker_client import OcrPageError
        if image.name.startswith("0001"):
            self.calls.append((language.name, image.name))
            raise OcrPageError("The text of this page couldn't be read: bad image")
        return super().read(language, image)


def test_a_page_the_ocr_cant_read_doesnt_stop_the_comprehension(client, tmp_path, monkeypatch):
    worker = FailingWorker()
    monkeypatch.setattr(page_text, "_worker", worker)
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png", "2.png"])
    comic_id = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS).json["comic"]["id"]
    client.get(f"/reader/api/comics/{comic_id}/comprehension")
    wait_for_background_reading()
    # the page that failed is tried again once…
    retry = client.get(f"/reader/api/comics/{comic_id}/comprehension").json
    assert retry["comprehension"] is None and retry["read"] == 1
    wait_for_background_reading()
    assert len(worker.calls) == 3
    # …then the comprehension is made without it
    done = client.get(f"/reader/api/comics/{comic_id}/comprehension").json
    assert done["read"] == 2 and done["failed"] == 1 and done["comprehension"] is not None and not done.get("error")
    assert len(worker.calls) == 3
    client.get(f"/reader/api/comics/{comic_id}/pages/1/text")
    assert len(worker.calls) == 4  # read again when it's shown


def test_background_reading_doesnt_write_into_a_removed_comic(client, tmp_path, monkeypatch):
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png"])
    comic_id = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS).json["comic"]["id"]

    class RemovingWorker(FakeWorker):
        def read(self, language, image):
            comics.delete_comic(comic_id)  # while the page is read
            return super().read(language, image)

    monkeypatch.setattr(page_text, "_worker", RemovingWorker())
    client.get(f"/reader/api/comics/{comic_id}/comprehension")
    wait_for_background_reading()
    assert not (comics.comics_dir() / comic_id).exists()


def test_a_temporary_ocr_failure_is_tried_again(client, tmp_path, monkeypatch):
    from miningcat.infrastructure.ocr.worker_client import OcrWorkerError

    class BrokenWorker(FakeWorker):
        def read(self, language, image):
            raise OcrWorkerError("The text recognition stopped unexpectedly.")

    monkeypatch.setattr(page_text, "_worker", BrokenWorker())
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png"])
    comic_id = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS).json["comic"]["id"]
    client.get(f"/reader/api/comics/{comic_id}/comprehension")
    wait_for_background_reading()
    assert "stopped" in client.get(f"/reader/api/comics/{comic_id}/comprehension").json["error"]
    # the OCR works again (a page read in the reader): the comic is read
    monkeypatch.setattr(page_text, "_worker", FakeWorker())
    client.get(f"/reader/api/comics/{comic_id}/pages/1/text")
    assert client.get(f"/reader/api/comics/{comic_id}/comprehension").json["comprehension"] is not None


def test_comprehension_tells_why_pages_cant_be_read(client, tmp_path, monkeypatch):
    monkeypatch.setattr(page_text, "_worker", FakeWorker())
    archive = make_cbz(tmp_path / "neko.cbz", ["1.png"])
    comic_id = client.post("/reader/api/comics?name=neko.cbz", data=archive.read_bytes(), headers=HEADERS).json["comic"]["id"]
    client.post(f"/reader/api/comics/{comic_id}/prefs", json={"language": "ar"}, headers=HEADERS)
    res = client.get(f"/reader/api/comics/{comic_id}/comprehension").json
    assert res["comprehension"] is None and "isn't available" in res["error"]


def test_pdf_text_of_a_rotated_page_is_where_it_is_shown(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from miningcat.infrastructure.media.pdf_pages import page_lines
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((100, 150), "MMMM", fontsize=20)
    page.set_rotation(90)
    [[text, x, y, w, h]] = page_lines(page, 2)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
    assert text == "MMMM" and (pixmap.width, pixmap.height) == (800, 600)
    assert h > w and 480 < x < 520 and 190 < y < 210  # the line turned with the page (its ink: x 500-528, y 203-329)


def test_a_scan_with_a_few_words_of_text_is_read_by_ocr(library, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = make_pdf(tmp_path / "scan.pdf", ["red"])
    with pymupdf.open(pdf) as doc:
        doc[0].insert_text((5, 85), "p. 1", fontsize=4)  # a page number over the scan
        doc.save(tmp_path / "numbered.pdf")
    meta = comics.import_file(tmp_path / "numbered.pdf")
    assert not (comics.comics_dir() / meta["id"] / "text").exists()


def test_api_import_an_image(client, tmp_path):
    res = client.post("/reader/api/comics?name=sign.jpg", data=page_bytes("red", fmt="JPEG"), headers=HEADERS)
    assert res.status_code == 200, res.json
    listing = client.get("/reader/api/comics").json
    assert "png" in listing["images"] and "png" not in listing["extensions"]
    assert listing["comics"][0]["image"] and listing["comics"][0]["pages"] == 1
    assert client.post("/reader/api/comics?name=notes.txt", data=b"hello", headers=HEADERS).status_code == 400


def test_api_rejects_unknown_formats_and_ids(client):
    res = client.post("/reader/api/comics?name=book.docx", data=b"PK", headers=HEADERS)
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
    worker = OcrWorker()
    try:
        from miningcat.domain.languages import Language
        result = worker.read(Language.JAPANESE, tmp_path / "page.png")
    except comics.ComicError as exc:
        pytest.skip(f"OCR unavailable: {exc}")
    finally:
        worker._stop()
    assert any("猫" in line[0] for line in result["lines"])
