import io
import os
import sys
import zipfile

import pytest
from PIL import Image

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP_DIR)

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://bauch:***@localhost:55432/bauchbinden_test")


def make_png(size=(200, 400), color=(120, 200, 90, 255), corner_alpha=0):
    img = Image.new("RGBA", size, color)
    # punch a transparent corner so the alpha channel is meaningfully tested
    img.putpixel((0, 0), (0, 0, 0, corner_alpha))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture()
def client():
    import app as appmod
    from models import db

    with appmod.app.app_context():
        db.drop_all()
        db.create_all()
    appmod.app.config["TESTING"] = True
    with appmod.app.test_client() as c:
        yield c


def add_player(client, name="Hans Wurst", number="7", photo=True):
    data = {"name": name, "number": number}
    if photo:
        data["photo"] = (io.BytesIO(make_png()), "photo.png")
    return client.post("/players", data=data,
                       content_type="multipart/form-data")


def test_add_player_requires_name(client):
    assert client.post("/players", data={"name": "  "}).status_code == 400


def test_add_and_list_player(client):
    assert add_player(client).status_code == 201
    players = client.get("/api/players").get_json()
    assert players[0]["name"] == "Hans Wurst"
    assert players[0]["number"] == "7"
    assert players[0]["has_photo"] is True
    photo = client.get("/media/player/1/photo")
    assert photo.status_code == 200
    assert photo.mimetype == "image/png"


def test_player_without_photo(client):
    assert add_player(client, name="Ohne Foto", photo=False).status_code == 201
    resp = client.get("/banner.png")
    assert resp.status_code == 200


def test_banner_uses_configured_resolution(client):
    add_player(client)
    client.post("/settings", data={"width": "1280", "height": "720"})
    resp = client.get("/banner.png")
    assert resp.status_code == 200
    img = Image.open(io.BytesIO(resp.data))
    assert img.size == (1280, 720)
    assert img.mode == "RGBA"


def test_banner_is_transparent_at_corners(client):
    add_player(client)
    resp = client.get("/banner.png?width=800&height=450")
    img = Image.open(io.BytesIO(resp.data))
    assert img.getpixel((0, 0))[3] == 0
    assert img.getpixel((799, 0))[3] == 0


def test_banner_contains_content(client):
    add_player(client)
    resp = client.get("/banner.png?width=800&height=450")
    img = Image.open(io.BytesIO(resp.data))
    opaque = sum(img.getchannel("A").histogram()[1:])
    assert opaque > 1000  # the bug itself must be painted


def test_banner_query_override_and_validation(client):
    add_player(client)
    assert client.get("/banner.png?width=640&height=360").status_code == 200
    assert client.get("/banner.png?width=640").status_code == 400
    assert client.get("/banner.png?width=99999&height=99999").status_code == 400


def test_settings_logo_stored_and_used(client):
    add_player(client)
    resp = client.post("/settings",
                       data={"logo": (io.BytesIO(make_png((300, 300))), "logo.png"),
                             "accent": "#00AA88"},
                       content_type="multipart/form-data")
    assert resp.status_code == 204
    logo = client.get("/media/logo")
    assert logo.status_code == 200
    assert len(logo.data) > 0
    assert client.get("/banner.png").status_code == 200


def test_settings_rejects_bad_resolution(client):
    assert client.post("/settings", data={"width": "abc"}).status_code == 400
    assert client.post("/settings", data={"width": "10"}).status_code == 400


def test_export_zip_contains_all_players(client):
    add_player(client, name="Ada")
    add_player(client, name="Bert")
    resp = client.get("/export.zip")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert all(n.endswith(".png") for n in names)
        for n in names:
            img = Image.open(io.BytesIO(zf.read(n)))
            assert img.mode == "RGBA"


def test_duplicate_names_get_unique_zip_entries(client):
    add_player(client, name="Dupp")
    add_player(client, name="Dupp")
    with zipfile.ZipFile(io.BytesIO(client.get("/export.zip").data)) as zf:
        assert len(set(zf.namelist())) == 2


def test_preview_page_lists_players(client):
    add_player(client)
    resp = client.get("/preview")
    assert resp.status_code == 200
    assert b"Hans Wurst" in resp.data


def test_delete_player(client):
    add_player(client)
    assert client.post("/players/1/delete").status_code == 204
    assert client.get("/api/players").get_json() == []


def test_update_player(client):
    add_player(client)
    assert client.post("/players/1", data={"name": "Neuer Name"}).status_code == 204
    assert client.get("/api/players").get_json()[0]["name"] == "Neuer Name"
