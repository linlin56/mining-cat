import io
import zipfile

import pytest

pytest.importorskip("flask")

from web import app as web_app
from web import books
from web.state import AppState

HEADERS = {"X-MiningCat": "1"}


def make_epub(chapters, lang="ja", rtl=False, cover=True, title="テスト", encrypted=False) -> bytes:
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w")
    z.writestr("mimetype", "application/epub+zip")
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
               '<rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
    if encrypted:
        z.writestr("META-INF/encryption.xml", "<encryption><EncryptedData>x</EncryptedData></encryption>")
    items, spine, nav = [], [], []
    for i, (heading, body) in enumerate(chapters):
        name = f"text/ch{i}.xhtml"
        z.writestr(f"OEBPS/{name}",
                   '<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
                   'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>t</title><style>p{color:red}</style>'
                   f'<script>alert(1)</script></head><body><h1 id="top">{heading}</h1>{body}</body></html>')
        items.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{i}"/>')
        nav.append(f'<li><a href="{name}#top">{heading}</a></li>')
    z.writestr("OEBPS/nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
               f'<body><nav epub:type="toc"><ol>{"".join(nav)}</ol></nav></body></html>')
    items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    if cover:
        z.writestr("OEBPS/img/cover.png", b"\x89PNG fake")
        items.append('<item id="cov" href="img/cover.png" media-type="image/png" properties="cover-image"/>')
    ppd = ' page-progression-direction="rtl"' if rtl else ""
    z.writestr("OEBPS/content.opf",
               '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               f'<dc:title>{title}</dc:title><dc:creator>作者</dc:creator><dc:language>{lang}</dc:language></metadata>'
               f'<manifest>{"".join(items)}</manifest><spine{ppd}>{"".join(spine)}</spine></package>')
    z.close()
    return buf.getvalue()


JA_CHAPTERS = [
    ("第一章", '<p>吾輩は<ruby>猫<rt>ねこ</rt></ruby>である。</p><p onclick="x()">名前は<a href="ch1.xhtml#note">まだ</a>無い。'
               '<img src="../img/cover.png"/><img src="../img/missing.png"/></p><p>ひらがなとカタカナのテストです。</p>'),
    ("第二章", '<p>どこで生れたかとんと見当がつかぬ。</p><aside id="note" epub:type="footnote"><p>注</p></aside>'),
]


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
    return app.test_client()


# ---------------------------------------------------------------- import

def test_epub_import(library):
    meta = books.import_book("neko.epub", make_epub(JA_CHAPTERS, rtl=True))
    assert meta["title"] == "テスト"
    assert meta["author"] == "作者"
    assert meta["language"] == "ja"
    assert meta["writing"] == "vertical"  # right-to-left page progression in a Japanese book
    assert [c["title"] for c in meta["chapters"]] == ["第一章", "第二章"]
    assert meta["toc"][0] == {"title": "第一章", "chapter": 0, "anchor": "c-top", "depth": 0}
    assert meta["cover"].endswith("/res/OEBPS/img/cover.png")
    assert meta["total_chars"] == sum(c["chars"] for c in meta["chapters"])

    html = books.chapter_html(meta["id"], 0)
    assert "<script" not in html and "<style" not in html and "onclick" not in html and "alert" not in html
    assert "<ruby>猫<rt>ねこ</rt></ruby>" in html
    assert 'id="c-top"' in html
    assert 'data-chapter="1" data-anchor="c-note"' in html
    assert html.count("<img") == 1  # the missing image is dropped
    assert "xmlns" not in html
    assert 'data-epub-type="footnote"' in books.chapter_html(meta["id"], 1)


def test_character_count_ignores_ruby():
    from lxml import etree
    root = etree.fromstring("<div><p>吾輩は<ruby>猫<rt>ねこ</rt></ruby>である。</p> <p>  </p></div>")
    assert books.count_chars(root) == len("吾輩は猫である。")


def test_wrong_metadata_language_is_corrected(library):
    meta = books.import_book("x.epub", make_epub(JA_CHAPTERS, lang="fr"))
    assert meta["language"] == "ja"


def test_horizontal_by_default(library):
    meta = books.import_book("fr.epub", make_epub([("Chapitre 1", "<p>Le chat est sur la table et il dort.</p>" * 5)], lang="fr"))
    assert meta["writing"] == "horizontal"
    assert meta["language"] == "fr"


def test_drm_epub_is_refused(library):
    with pytest.raises(books.BookError, match="DRM"):
        books.import_book("drm.epub", make_epub(JA_CHAPTERS, encrypted=True))
    assert not any((library / "books").iterdir())


def test_broken_epub_is_refused(library):
    with pytest.raises(books.BookError):
        books.import_book("broken.epub", b"not a zip")


def test_same_file_is_imported_once(library):
    data = make_epub(JA_CHAPTERS)
    first = books.import_book("a.epub", data)
    second = books.import_book("b.epub", data)
    assert first["id"] == second["id"]
    assert len(books.list_books()) == 1


def test_txt_big5_with_chapters(library):
    text = "測試小說\n\n第1章　開始\n　　這是第一章。他說：「你好！」\n第2章　結束\n　　這是第二章。我們走吧。\n"
    meta = books.import_book("小說.txt", text.encode("big5"))
    assert meta["title"] == "小說"
    assert meta["language"] == "zh-Hant"
    assert [c["title"] for c in meta["chapters"]] == ["測試小說", "第1章　開始", "第2章　結束"]
    assert [t["chapter"] for t in meta["toc"]] == [1, 2]
    assert "<h2>第1章　開始</h2>" in books.chapter_html(meta["id"], 1)


def test_txt_without_headings_is_split_in_parts(library, monkeypatch):
    monkeypatch.setattr(books, "TXT_PART_CHARS", 100)
    text = "\n\n".join("这是一个很长的段落，用来测试分段。" * 3 for _ in range(20))
    meta = books.import_book("long.txt", text.encode("utf-8"))
    assert meta["language"] == "zh-Hans"
    assert len(meta["chapters"]) > 3
    assert meta["chapters"][1]["title"] == "Part 2"


def test_txt_utf16_and_html_escaping(library):
    meta = books.import_book("a.txt", "Hello <b>world</b> & the cat\n".encode("utf-16"))
    assert "&lt;b&gt;world&lt;/b&gt; &amp;" in books.chapter_html(meta["id"], 0)


def test_html_book(library):
    page = b'<html lang="ko"><head><title>Doc</title><script>x</script></head><body><p>\xec\x95\x88\xeb\x85\x95\xed\x95\x98\xec\x84\xb8\xec\x9a\x94</p></body></html>'
    meta = books.import_book("doc.html", page)
    assert meta["title"] == "Doc"
    assert meta["language"] == "ko"
    assert "<script" not in books.chapter_html(meta["id"], 0)


def test_unsupported_format(library):
    with pytest.raises(books.BookError, match="Unsupported"):
        books.import_book("x.pdf", b"%PDF")


def test_language_detection():
    assert books.detect_language("これはテストです。ひらがなとカタカナ。" * 3) == "ja"
    assert books.detect_language("안녕하세요. 저는 테스트 파일입니다." * 3) == "ko"
    assert books.detect_language("這是一個測試。我們說話。" * 5) == "zh-Hant"
    assert books.detect_language("这是一个测试。我们说话。" * 5) == "zh-Hans"
    assert books.detect_language("Le chat est sur la table et les enfants sont dans le jardin. " * 3) == "fr"


# ---------------------------------------------------------------- progress, prefs, settings

def test_progress_and_prefs(library):
    meta = books.import_book("neko.epub", make_epub(JA_CHAPTERS))
    saved = books.save_progress(meta["id"], 7, 12, 150)
    assert (saved["chapter"], saved["offset"], saved["percent"]) == (1, 12, 100.0)
    assert books.get_progress(meta["id"])["offset"] == 12
    assert books.list_books()[0]["percent"] == 100.0

    assert books.save_prefs(meta["id"], {"writing": "horizontal", "language": "zh-Hant"}) == {"writing": "horizontal", "language": "zh-Hant"}
    assert books.save_prefs(meta["id"], {"writing": "sideways"})["writing"] == "horizontal"
    with pytest.raises(books.BookError):
        books.save_prefs(meta["id"], {"language": "<script>"})


def test_settings_are_clamped(library):
    settings = books.save_settings({"font_size": 500, "theme": "neon", "furigana": 0, "margin": "12"})
    assert settings["font_size"] == 48
    assert settings["theme"] == "light"
    assert settings["furigana"] is False
    assert settings["margin"] == 12
    assert books.get_settings() == settings


def test_book_ids_are_validated(library):
    with pytest.raises(books.BookError):
        books.get_meta("../../etc")


def test_old_renders_are_refreshed(library, monkeypatch):
    meta = books.import_book("neko.epub", make_epub(JA_CHAPTERS))
    monkeypatch.setattr(books, "RENDER_VERSION", books.RENDER_VERSION + 1)
    assert books.get_meta(meta["id"])["render_version"] == books.RENDER_VERSION


# ---------------------------------------------------------------- HTTP API

def test_reader_api_flow(client, library):
    client.post("/api/profile", json={"language": "ja"}, headers=HEADERS)
    assert client.get("/reader/").status_code == 200
    data = {"files": [(io.BytesIO(make_epub(JA_CHAPTERS)), "neko.epub"), (io.BytesIO(b"x"), "notes.pdf")]}
    res = client.post("/reader/api/books", data=data, headers=HEADERS, content_type="multipart/form-data").get_json()
    assert len(res["added"]) == 1
    assert res["errors"] and "notes.pdf" in res["errors"][0]
    book_id = res["added"][0]["id"]

    listing = client.get("/reader/api/books").get_json()
    assert [b["id"] for b in listing["books"]] == [book_id]
    assert "epub" in listing["extensions"]

    book = client.get(f"/reader/api/books/{book_id}").get_json()
    assert book["book"]["title"] == "テスト" and book["progress"] == {} and book["prefs"] == {}
    assert "猫" in client.get(f"/reader/api/books/{book_id}/chapters/0").get_json()["html"]
    assert client.get(f"/reader/api/books/{book_id}/chapters/9").status_code == 400
    assert client.get(book["book"]["cover"]).data == b"\x89PNG fake"
    assert client.get(f"/reader/api/books/{book_id}/res/../meta.json").status_code in (400, 404)

    assert client.post(f"/reader/api/books/{book_id}/progress", json={"chapter": 1, "offset": 3, "percent": 60}).status_code == 403
    progress = client.post(f"/reader/api/books/{book_id}/progress", json={"chapter": 1, "offset": 3, "percent": 60}, headers=HEADERS).get_json()
    assert progress["chapter"] == 1
    assert client.post(f"/reader/api/books/{book_id}/prefs", json={"writing": "vertical"}, headers=HEADERS).get_json() == {"writing": "vertical"}

    settings = client.post("/reader/api/settings", json={"font_size": 24}, headers=HEADERS).get_json()
    assert settings["font_size"] == 24
    assert client.get("/reader/api/settings").get_json()["font_size"] == 24

    assert client.post(f"/reader/api/books/{book_id}/delete", json={}, headers=HEADERS).get_json() == {"deleted": True}
    assert client.get("/reader/api/books").get_json()["books"] == []
