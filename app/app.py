"""Spieler-Bauchbinden — broadcast name-banner generator.

Keeps the roster in Postgres (player photos and the club logo stored as
BLOBs), renders transparent PNG bugs at the configured broadcast
resolution, and exports all banners as one ZIP.
"""
import io
import os
import time
import zipfile

from flask import (Flask, abort, jsonify, render_template, request,
                   Response)
from PIL import Image, UnidentifiedImageError

from banner import DEFAULT_ACCENT, DEFAULT_BAR, render_banner, slugify
from models import Player, Setting, db, get_logo, get_resolution

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://bauch:bauch@db:5432/bauchbinden")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def _image_or_none(data):
    """Validate upload bytes as an image; returns data or None."""
    if not data:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except (UnidentifiedImageError, OSError):
        return None
    return data


def _read_upload(name):
    f = request.files.get(name)
    if f is None or not f.filename:
        return None
    data = f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        abort(400, f"{name}: file too large (max 8 MB)")
    if _image_or_none(data) is None:
        abort(400, f"{name}: not a readable image — upload PNG/JPEG "
                   f"(SVG must be exported to PNG first)")
    return data


def _settings_dict():
    width, height = get_resolution()
    return {
        "width": width,
        "height": height,
        "accent": Setting.get_text("accent", DEFAULT_ACCENT),
        "bar_color": Setting.get_text("bar_color", DEFAULT_BAR),
        "has_logo": get_logo() is not None,
    }


def _banner_for(player, width=None, height=None):
    settings = _settings_dict()
    return render_banner(
        name=player.name,
        number=player.number or None,
        logo_png=get_logo(),
        photo_png=player.photo,
        width=width or settings["width"],
        height=height or settings["height"],
        accent=settings["accent"],
        bar_color=settings["bar_color"],
    )


def _png_response(png_bytes):
    return Response(png_bytes, mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


@app.get("/")
def control():
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    return render_template("control.html", players=players,
                           settings=_settings_dict())


@app.post("/players")
def add_player():
    name = (request.form.get("name") or "").strip()
    if not name:
        abort(400, "player name is required")
    last = db.session.query(db.func.max(Player.sort_order)).scalar() or 0
    player = Player(name=name, number=(request.form.get("number") or "").strip() or None,
                    photo=_read_upload("photo"), sort_order=last + 1)
    db.session.add(player)
    db.session.commit()
    return ("", 303, {"Location": "/"}) if _wants_redirect() else ("", 201)


@app.post("/players/<int:player_id>/delete")
def delete_player(player_id):
    player = db.session.get(Player, player_id) or abort(404)
    db.session.delete(player)
    db.session.commit()
    return ("", 303, {"Location": "/"}) if _wants_redirect() else ("", 204)


@app.post("/players/<int:player_id>")
def update_player(player_id):
    player = db.session.get(Player, player_id) or abort(404)
    if "name" in request.form:
        name = request.form["name"].strip()
        if not name:
            abort(400, "player name is required")
        player.name = name
    if "number" in request.form:
        player.number = request.form["number"].strip() or None
    photo = _read_upload("photo")
    if photo:
        player.photo = photo
    db.session.commit()
    return ("", 303, {"Location": "/"}) if _wants_redirect() else ("", 204)


def _wants_redirect():
    return request.form.get("_form") == "1"


def _save_int_setting(key, raw):
    try:
        value = int(raw)
    except ValueError:
        abort(400, f"invalid {key}")
        return
    if not 64 <= value <= 7680:
        abort(400, f"{key} out of range")
        return
    Setting.set_text(key, str(value))


@app.post("/settings")
def save_settings():
    logo = _read_upload("logo")
    if logo:
        Setting.set_blob("logo", logo)
    for field in ("width", "height"):
        raw = request.form.get(field)
        if raw:
            _save_int_setting(field, raw)
    for field, key in (("accent", "accent"), ("bar_color", "bar_color")):
        raw = request.form.get(field)
        if raw:
            Setting.set_text(key, raw.strip())
    return ("", 303, {"Location": "/"}) if _wants_redirect() else ("", 204)


@app.get("/media/logo")
def media_logo():
    logo = get_logo()
    if not logo:
        abort(404)
    return _png_response(logo)


@app.get("/media/player/<int:player_id>/photo")
def media_photo(player_id):
    player = db.session.get(Player, player_id) or abort(404)
    if not player.photo:
        abort(404)
    return _png_response(player.photo)


@app.get("/banner.png")
def banner_png():
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    if not players:
        abort(404, "no players defined")
    pid = request.args.get("player_id", type=int)
    player = next((p for p in players if p.id == pid), players[0]) if pid else players[0]
    width = request.args.get("width", type=int)
    height = request.args.get("height", type=int)
    if (width is None) != (height is None):
        abort(400, "width and height must be given together")
    for dim in (width, height):
        if dim is not None and not 64 <= dim <= 7680:
            abort(400, "resolution out of range")
    return _png_response(_banner_for(player, width, height))


@app.get("/preview")
def preview():
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    return render_template("preview.html", players=players,
                           settings=_settings_dict())


@app.get("/export.zip")
def export_zip():
    width = request.args.get("width", type=int)
    height = request.args.get("height", type=int)
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    if not players:
        abort(404, "no players defined")
    buf = io.BytesIO()
    used = set()
    w, h = width or _settings_dict()["width"], height or _settings_dict()["height"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for player in players:
            base = f"{slugify(player.name)}_{w}x{h}"
            fname = base + ".png"
            n = 2
            while fname in used:
                fname = f"{base}_{n}.png"
                n += 1
            used.add(fname)
            zf.writestr(fname, _banner_for(player, width, height))
    return send_response_bytes(buf.getvalue(),
                               "application/zip",
                               f"attachment; filename=bauchbinden_{w}x{h}.zip")


def send_response_bytes(data, mimetype, disposition):
    return Response(data, mimetype=mimetype,
                    headers={"Content-Disposition": disposition,
                             "Cache-Control": "no-store"})


@app.get("/api/players")
def api_players():
    players = Player.query.order_by(Player.sort_order, Player.id).all()
    return jsonify([p.to_dict() for p in players])


def _create_tables(retries=10, delay=1.0):
    """Create tables, retrying while Postgres is still booting (compose)."""
    for attempt in range(retries):
        try:
            with app.app_context():
                db.create_all()
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


_create_tables()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
