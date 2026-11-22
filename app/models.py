"""Database models. All images (logo and player photos) are stored as
bytea blobs inside Postgres — no object storage, no volume to back up.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080


class Player(db.Model):
    __tablename__ = "player"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    number = db.Column(db.String(8))
    photo = db.Column(db.LargeBinary)          # PNG with alpha
    sort_order = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "number": self.number,
                "has_photo": self.photo is not None}


class Setting(db.Model):
    """Simple key/value store for the shared banner assets and options."""

    __tablename__ = "setting"

    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.LargeBinary)
    text = db.Column(db.Text)

    @classmethod
    def get_text(cls, key, default=None):
        row = db.session.get(cls, key)
        return row.text if row and row.text is not None else default

    @classmethod
    def set_text(cls, key, value):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.text = value
        db.session.commit()

    @classmethod
    def get_blob(cls, key):
        row = db.session.get(cls, key)
        return row.value if row else None

    @classmethod
    def set_blob(cls, key, blob):
        row = db.session.get(cls, key)
        if row is None:
            row = cls(key=key)
            db.session.add(row)
        row.value = blob
        db.session.commit()


def get_logo():
    return Setting.get_blob("logo")


def get_resolution():
    w = int(Setting.get_text("width", str(DEFAULT_WIDTH)) or DEFAULT_WIDTH)
    h = int(Setting.get_text("height", str(DEFAULT_HEIGHT)) or DEFAULT_HEIGHT)
    return w, h
