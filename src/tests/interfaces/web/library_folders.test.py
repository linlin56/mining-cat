import io

import pytest

pytest.importorskip("flask")
from PIL import Image

from miningcat.application.library import folders
from miningcat.interfaces.web import app as web_app
from miningcat.interfaces.web.jobs import AppState

HEADERS = {"X-MiningCat": "1"}


@pytest.fixture
def client():
    app = web_app.create_app(AppState())
    app.testing = True
    client = app.test_client()
    client.post("/api/profile", json={"language": "ja"}, headers=HEADERS)
    return client


def image_bytes(color):
    buf = io.BytesIO()
    Image.new("RGB", (60, 90), color).save(buf, "PNG")
    return buf.getvalue()


def import_image(client, color) -> str:
    res = client.post("/reader/api/comics?name=page.png", data=image_bytes(color), headers=HEADERS)
    assert res.status_code == 200, res.json
    return res.json["comic"]["id"]


def test_create_rename_and_delete_a_folder(client):
    folder = client.post("/reader/api/folders", json={"name": "  Manga   2026 "}, headers=HEADERS).json["folder"]
    assert folder["name"] == "Manga 2026" and folder["language"] == "ja"
    assert client.get("/reader/api/folders").json["folders"][folder["id"]]["name"] == "Manga 2026"

    client.post(f"/reader/api/folders/{folder['id']}", json={"name": "Manga"}, headers=HEADERS)
    assert client.get("/reader/api/folders").json["folders"][folder["id"]]["name"] == "Manga"

    assert client.post(f"/reader/api/folders/{folder['id']}/delete", json={}, headers=HEADERS).json["deleted"]
    assert client.get("/reader/api/folders").json["folders"] == {}


def test_a_folder_needs_a_name(client):
    res = client.post("/reader/api/folders", json={"name": "   "}, headers=HEADERS)
    assert res.status_code == 400 and res.json["title"] == "Folders"


def test_move_items_in_and_out_of_a_folder(client):
    comic_id = import_image(client, "red")
    folder_id = client.post("/reader/api/folders", json={"name": "Signs"}, headers=HEADERS).json["folder"]["id"]
    client.post("/reader/api/folders/move", json={"items": [{"kind": "comic", "id": comic_id}], "folder": folder_id}, headers=HEADERS)
    assert client.get("/reader/api/folders").json["items"] == {f"comic:{comic_id}": folder_id}

    client.post("/reader/api/folders/move", json={"items": [{"kind": "comic", "id": comic_id}], "folder": None}, headers=HEADERS)
    assert client.get("/reader/api/folders").json["items"] == {}


def test_deleting_a_folder_keeps_what_it_held(client):
    comic_id = import_image(client, "red")
    folder_id = client.post("/reader/api/folders", json={"name": "Signs"}, headers=HEADERS).json["folder"]["id"]
    client.post("/reader/api/folders/move", json={"items": [{"kind": "comic", "id": comic_id}], "folder": folder_id}, headers=HEADERS)
    client.post(f"/reader/api/folders/{folder_id}/delete", json={}, headers=HEADERS)
    assert client.get("/reader/api/folders").json["items"] == {}
    assert [c["id"] for c in client.get("/reader/api/comics").json["comics"]] == [comic_id]


def test_a_deleted_comic_leaves_its_folder(client):
    comic_id = import_image(client, "red")
    folder_id = folders.create_folder("Signs", "ja")["id"]
    folders.move([{"kind": "comic", "id": comic_id}], folder_id)
    client.post(f"/reader/api/comics/{comic_id}/delete", json={}, headers=HEADERS)
    assert folders.list_folders("ja")["items"] == {}


def test_unknown_folders_and_items_are_refused(client):
    res = client.post("/reader/api/folders/move", json={"items": [{"kind": "comic", "id": "0" * 16}], "folder": "nope"}, headers=HEADERS)
    assert res.status_code == 400
    folder_id = folders.create_folder("Signs")["id"]
    res = client.post("/reader/api/folders/move", json={"items": [{"kind": "video", "id": "../../x"}], "folder": folder_id}, headers=HEADERS)
    assert res.status_code == 400


def test_folders_belong_to_the_language_studied(client):
    folders.create_folder("Japanese", "ja")
    folders.create_folder("Korean", "ko")
    folders.create_folder("Any", "")
    names = sorted(f["name"] for f in client.get("/reader/api/folders").json["folders"].values())
    assert names == ["Any", "Japanese"]


# ---------------------------------------------------------------- folders in folders

def test_folders_go_into_folders(client):
    manga = folders.create_folder("Manga", "ja")["id"]
    res = client.post("/reader/api/folders", json={"name": "One Piece", "parent": manga}, headers=HEADERS)
    one_piece = res.json["folder"]["id"]
    assert client.get("/reader/api/folders").json["folders"][one_piece]["parent"] == manga
    # out of Manga, into the library
    client.post("/reader/api/folders/move", json={"items": [{"kind": "folder", "id": one_piece}], "folder": None}, headers=HEADERS)
    assert client.get("/reader/api/folders").json["folders"][one_piece]["parent"] is None


def test_a_folder_never_goes_into_itself_or_its_folders(client):
    a = folders.create_folder("A", "ja")["id"]
    b = folders.create_folder("B", "ja", parent=a)["id"]
    c = folders.create_folder("C", "ja", parent=b)["id"]
    for target in (a, c):
        res = client.post("/reader/api/folders/move", json={"items": [{"kind": "folder", "id": a}], "folder": target}, headers=HEADERS)
        assert res.status_code == 400
    assert folders.list_folders("ja")["folders"][a]["parent"] is None


def test_deleting_a_folder_moves_what_it_held_up(client):
    comic_id = import_image(client, "red")
    a = folders.create_folder("A", "ja")["id"]
    b = folders.create_folder("B", "ja", parent=a)["id"]
    c = folders.create_folder("C", "ja", parent=b)["id"]
    folders.move([{"kind": "comic", "id": comic_id}], b)
    client.post(f"/reader/api/folders/{b}/delete", json={}, headers=HEADERS)
    listing = client.get("/reader/api/folders").json
    assert listing["folders"][c]["parent"] == a and listing["items"] == {f"comic:{comic_id}": a}


def test_a_folder_of_another_language_is_never_a_parent_shown(client):
    korean = folders.create_folder("Korean", "ko")["id"]
    child = folders.create_folder("Any", "", parent=korean)["id"]
    assert client.get("/reader/api/folders").json["folders"][child]["parent"] is None


# ---------------------------------------------------------------- albums

def test_a_picture_dropped_on_a_picture_makes_an_album(client):
    first, second, third = import_image(client, "red"), import_image(client, "green"), import_image(client, "blue")
    folder_id = folders.create_folder("Signs", "ja")["id"]
    folders.move([{"kind": "comic", "id": first}, {"kind": "comic", "id": second}], folder_id)

    album = client.post(f"/reader/api/comics/{first}/append", json={"image": second}, headers=HEADERS).json["comic"]
    assert album["album"] and not album["image"] and [p["file"] for p in album["pages"]] == ["0001.png", "0002.png"]
    album_id = album["id"]
    assert album_id != first  # the picture's fingerprint is the picture's
    album = client.post(f"/reader/api/comics/{album_id}/append", json={"image": third}, headers=HEADERS).json["comic"]
    assert len(album["pages"]) == 3 and album["id"] == album_id

    listing = client.get("/reader/api/comics").json["comics"]
    assert [(c["id"], c["pages"], c["album"]) for c in listing] == [(album_id, 3, True)]
    # the album keeps the folder of the first picture; the pictures added leave theirs
    assert client.get("/reader/api/folders").json["items"] == {f"comic:{album_id}": folder_id}
    page = client.get(f"/reader/api/comics/{album_id}/pages/2")
    with Image.open(io.BytesIO(page.data)) as img:
        assert img.getpixel((5, 5))[1] > 100  # the green one


def test_only_pictures_go_into_albums(client, tmp_path):
    import zipfile
    picture = import_image(client, "red")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("1.png", image_bytes("green"))
        zf.writestr("2.png", image_bytes("blue"))
    comic = client.post("/reader/api/comics?name=vol1.cbz", data=archive.getvalue(), headers=HEADERS).json["comic"]["id"]
    assert client.post(f"/reader/api/comics/{comic}/append", json={"image": picture}, headers=HEADERS).status_code == 400
    assert client.post(f"/reader/api/comics/{picture}/append", json={"image": comic}, headers=HEADERS).status_code == 400
    assert client.post(f"/reader/api/comics/{picture}/append", json={"image": picture}, headers=HEADERS).status_code == 400
    assert len(client.get("/reader/api/comics").json["comics"]) == 2


def test_importing_the_first_picture_of_an_album_again_gives_the_picture(client):
    first, second = import_image(client, "red"), import_image(client, "green")
    album_id = client.post(f"/reader/api/comics/{first}/append", json={"image": second}, headers=HEADERS).json["comic"]["id"]
    res = client.post("/reader/api/comics?name=page.png", data=image_bytes("red"), headers=HEADERS).json["comic"]
    assert res["id"] == first and res["new"] and res["image"]
    assert sorted(c["pages"] for c in client.get("/reader/api/comics").json["comics"]) == [1, 2]
    again = client.post("/reader/api/comics?name=page.png", data=image_bytes("red"), headers=HEADERS).json["comic"]
    assert again["id"] == first and not again["new"]
    assert client.get(f"/reader/api/comics/{album_id}").status_code == 200


def test_an_album_reads_its_progress_out_of_its_new_number_of_pages(client):
    first, second = import_image(client, "red"), import_image(client, "green")
    assert client.post(f"/reader/api/comics/{first}/progress", json={"page": 1}, headers=HEADERS).json["percent"] == 100
    album_id = client.post(f"/reader/api/comics/{first}/append", json={"image": second}, headers=HEADERS).json["comic"]["id"]
    assert client.get(f"/reader/api/comics/{album_id}").json["progress"]["percent"] == 50
    assert client.get("/reader/api/comics").json["comics"][0]["percent"] == 50


def test_a_folder_of_pictures_makes_an_album_named_after_it(client):
    first, second, third = import_image(client, "red"), import_image(client, "green"), import_image(client, "blue")
    folder_id = folders.create_folder("Chapter 1", "ja")["id"]
    folders.move([{"kind": "comic", "id": first}, {"kind": "comic", "id": third}], folder_id)
    res = client.post("/reader/api/comics/album", json={"images": [first, second, second, third], "title": " Chapter 1 "},
                      headers=HEADERS)
    album = res.json["comic"]
    assert album["album"] and album["title"] == "Chapter 1" and len(album["pages"]) == 3
    assert [(c["id"], c["pages"]) for c in client.get("/reader/api/comics").json["comics"]] == [(album["id"], 3)]
    # the album goes where the importer puts it: none of the pictures' folders is kept
    assert client.get("/reader/api/folders").json["items"] == {}
    page = client.get(f"/reader/api/comics/{album['id']}/pages/2")
    with Image.open(io.BytesIO(page.data)) as img:
        assert img.getpixel((5, 5))[1] > 100  # the green one


def test_an_album_needs_two_pictures(client):
    picture = import_image(client, "red")
    res = client.post("/reader/api/comics/album", json={"images": [picture, picture], "title": "One"}, headers=HEADERS)
    assert res.status_code == 400
    assert client.get(f"/reader/api/comics/{picture}").json["comic"]["image"]


def test_a_folder_without_an_id_is_refused(client):
    res = client.post("/reader/api/folders/move", json={"items": [{"kind": "folder"}], "folder": None}, headers=HEADERS)
    assert res.status_code == 400 and res.json["title"] == "Folders"


def test_deleting_what_is_in_no_folder_leaves_the_folders_alone(client):
    from miningcat.config.paths import paths
    comic_id = import_image(client, "red")
    client.post(f"/reader/api/comics/{comic_id}/delete", json={}, headers=HEADERS)
    assert not paths.reader_folders.exists()


def test_a_book_imported_again_is_not_new(client):
    upload = lambda: {"files": (io.BytesIO("吾輩は猫である。名前はまだ無い。".encode()), "neko.txt")}
    first = client.post("/reader/api/books", data=upload(), headers=HEADERS).json["added"]
    again = client.post("/reader/api/books", data=upload(), headers=HEADERS).json["added"]
    assert first[0]["new"] and not again[0]["new"] and first[0]["id"] == again[0]["id"]
