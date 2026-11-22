"""Broadcast name-banner (bug) renderer.

Draws a transparent full-resolution canvas with the name bug positioned
bottom-left, so the PNG can be dropped straight into OBS / vMix /
ATEM as a media source keyed over the live picture.

All geometry scales from the frame height, so one renderer serves
720p through 4K broadcasts.
"""
import io
import math
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
BOLD_FONT = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
REG_FONT = os.path.join(FONT_DIR, "DejaVuSans.ttf")
TEXTURE_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "texture.png")

DEFAULT_ACCENT = "#E4392B"
DEFAULT_BAR = "#0C101C"
TEXT_COLOR = "#FFFFFF"
BAR_ALPHA = 232
TEXTURE_ALPHA = 0.18  # site uses 0.07 on huge hero areas; on a small bug
# that is invisible against #0C101C, so we push it into a visible range
TEXTURE_TILE = 4.5    # tile side in bar-height units -> readable arc cells

# The site's .golden-gradient, verbatim: linear-gradient(227deg, ...).
GOLD_STOPS = [
    (0.1609, (226, 175, 64)), (0.2306, (233, 188, 96)),
    (0.3568, (245, 210, 148)), (0.4519, (252, 224, 180)),
    (0.5043, (255, 229, 192)), (0.5698, (250, 219, 169)),
    (0.7057, (237, 195, 112)), (0.8340, (224, 170, 52)),
]
GOLD_ANGLE = 227.0


def _font(path, size):
    # Load through BytesIO on purpose: ImageFont.truetype(path) silently
    # falls back to same-named SYSTEM fonts when the file is unreadable,
    # which hides corrupt/vendored-font bugs in environments that happen
    # to ship a DejaVu (Docker slim images do not — CI would pass and
    # production would crash with "unknown file format").
    with open(path, "rb") as fh:
        return ImageFont.truetype(io.BytesIO(fh.read()), max(8, int(size)))


def _hex_rgb(value, default_rgb):
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return default_rgb
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default_rgb


def _load_image(data):
    if not data:
        return None
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def _fit_text(text, font, max_width, draw):
    """Return text truncated with an ellipsis to fit max_width."""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "\u2026"
    while text and draw.textlength(text + ellipsis, font=font) > max_width:
        text = text[:-1]
    return text + ellipsis


def _paste_rgba(canvas, img, xy):
    canvas.alpha_composite(img.convert("RGBA"), dest=xy)


def _ramp_color(t):
    """Interpolate GOLD_STOPS (CSS semantics: flat outside first/last stop)."""
    if t <= GOLD_STOPS[0][0]:
        return GOLD_STOPS[0][1]
    if t >= GOLD_STOPS[-1][0]:
        return GOLD_STOPS[-1][1]
    for (t0, c0), (t1, c1) in zip(GOLD_STOPS, GOLD_STOPS[1:]):
        if t0 <= t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(round(c0[i] + f * (c1[i] - c0[i])) for i in range(3))
    return GOLD_STOPS[-1][1]


def _gradient_rect(w, h, angle_deg=GOLD_ANGLE):
    """CSS-style linear-gradient over a w x h box, rendered small + upscaled.

    CSS angle: 0deg points up, clockwise; gradient line through the center
    with length |w*sin| + |h*cos|.
    """
    th = math.radians(angle_deg)
    dx, dy = math.sin(th), -math.cos(th)          # y-down screen space
    length = abs(w * dx) + abs(h * dy)
    n = max(64, min(512, int(length)))
    ramp = Image.new("RGB", (n, 1))
    px = ramp.load()
    if px is not None:
        for i in range(n):
            px[i, 0] = _ramp_color(i / (n - 1))
    # Image.transform maps to SOURCE PIXEL space: u_pix in [0, n-1] along
    # the CSS gradient line through the box center.
    scale = (n - 1) / max(1.0, length)
    a, b = dx * scale, dy * scale
    c = (n - 1) * 0.5 - (w * dx + h * dy) * scale / 2.0
    grad = ramp.transform((w, h), Image.Transform.AFFINE,
                          (a, b, c, 0.0, 0.0, 0.5),
                          resample=Image.Resampling.BILINEAR)
    return grad.convert("RGBA")


def _texture_layer(w, h, tile_side):
    """Tile the handballsociety.com texture at 7% alpha for a w x h area."""
    tex = _load_image(_read_file(TEXTURE_PNG))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if tex is None:
        return layer
    side = max(16, int(tile_side))
    tex = tex.resize((side, side), Image.Resampling.LANCZOS)
    alpha = tex.split()[3].point(lambda v: int(v * TEXTURE_ALPHA))
    tex.putalpha(alpha)
    for ty in range(0, h, side):
        for tx in range(0, w, side):
            layer.alpha_composite(tex, (tx, ty))
    return layer


def _read_file(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def render_banner(name, number=None, logo_png=None, photo_png=None,
                  width=1920, height=1080, accent=DEFAULT_ACCENT,
                  bar_color=DEFAULT_BAR):
    """Render one transparent PNG bug for the given player.

    name       display name (uppercase in the bar)
    number     jersey number shown in the accent chip (optional)
    logo_png   PNG bytes with alpha (optional)
    photo_png  PNG bytes with alpha (optional)
    width/height  broadcast frame resolution
    """
    width, height = int(width), int(height)
    accent_rgb = _hex_rgb(accent, (0xE4, 0x39, 0x2B))
    bar_rgb = _hex_rgb(bar_color, (0x0C, 0x10, 0x1C))

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    probe = ImageDraw.Draw(canvas)

    bar_h = round(height * 0.10)
    margin_b = round(height * 0.045)
    margin_l = round(width * 0.045)
    pad = round(bar_h * 0.42)

    name_text = _fit_text(str(name or "").upper(), _font(BOLD_FONT, bar_h * 0.52),
                          int(width * 0.42), probe)
    name_font = _font(BOLD_FONT, bar_h * 0.52)

    photo = _load_image(photo_png)
    chip_w = round(bar_h * 0.95) if number not in (None, "") else 0

    # Photo block to the right of the bar, bottom-aligned, extends upwards.
    photo_w = 0
    if photo is not None:
        photo_h = round(bar_h * 2.6)
        photo_w = max(1, round(photo.width * photo_h / photo.height))
        photo = photo.resize((photo_w, photo_h), Image.Resampling.LANCZOS)

    logo = _load_image(logo_png)
    logo_w = 0
    if logo is not None:
        logo_h = round(bar_h * 0.72)
        logo_w = max(1, round(logo.width * logo_h / logo.height))
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

    text_w = round(probe.textlength(name_text, font=name_font)) if name_text else 0
    bar_w = pad + logo_w + (chip_w + pad if chip_w else 0) + text_w + pad
    frame_w = max(2, round(bar_h * 0.06))  # golden gradient frame thickness
    chip_pad = max(2, round(bar_h * 0.12))  # breathing room around number chip
    bar_w += 2 * frame_w
    photo_gap = round(bar_h * 0.12)

    bar_x = margin_l
    bar_y = height - margin_b - bar_h

    # Keep the whole bug inside the frame: shrink the photo if needed.
    if photo is not None:
        max_pw = width - 2 * margin_l - bar_w - photo_gap
        if max_pw < photo.width:
            ratio = max(0.05, max_pw / photo.width)
            photo = photo.resize(
                (max(1, int(photo.width * ratio)),
                 max(1, int(photo.height * ratio))),
                Image.Resampling.LANCZOS)

    # Golden gradient frame (handballsociety.com .golden-gradient) around a
    # dark, texture-patterned name field. Square corners, no bottom strip.
    bar = _gradient_rect(bar_w, bar_h)
    inner_w = bar_w - 2 * frame_w
    inner_h = bar_h - 2 * frame_w
    inner = Image.new("RGBA", (inner_w, inner_h), (*bar_rgb, BAR_ALPHA))
    inner.alpha_composite(_texture_layer(inner_w, inner_h, bar_h * TEXTURE_TILE))
    bar.alpha_composite(inner, dest=(frame_w, frame_w))
    canvas.alpha_composite(bar, dest=(bar_x, bar_y))

    draw = ImageDraw.Draw(canvas)
    cursor = bar_x + frame_w + pad

    if logo is not None:
        _paste_rgba(canvas, logo, (cursor, bar_y + (bar_h - logo.height) // 2))
        cursor += logo_w + pad

    if chip_w:
        box_w = chip_w - 2 * chip_pad
        box_h = bar_h - 2 * frame_w - 2 * chip_pad
        chip = Image.new("RGBA", (chip_w, bar_h - 2 * frame_w), (0, 0, 0, 0))
        chip_draw = ImageDraw.Draw(chip)
        chip_draw.rectangle([chip_pad, chip_pad, chip_pad + box_w - 1,
                             chip_pad + box_h - 1], fill=(*accent_rgb, 255))
        num_font = _font(BOLD_FONT, bar_h * 0.50)
        num_text = str(number)
        bb = chip_draw.textbbox((0, 0), num_text, font=num_font)
        chip_draw.text((chip_pad + (box_w - (bb[2] - bb[0])) / 2 - bb[0],
                        chip_pad + (box_h - (bb[3] - bb[1])) / 2 - bb[1]),
                       num_text, font=num_font, fill=TEXT_COLOR)
        canvas.alpha_composite(chip, dest=(cursor, bar_y + frame_w))
        cursor += chip_w + pad

    if name_text:
        bb = draw.textbbox((0, 0), name_text, font=name_font)
        draw.text((cursor, bar_y + (bar_h - (bb[3] - bb[1])) / 2 - bb[1]),
                  name_text, font=name_font, fill=TEXT_COLOR)

    if photo is not None:
        # Photo block sits to the right of the bar, bottom-aligned with it
        # and extending upwards — classic headshot-bug style.
        _paste_rgba(canvas, photo, (bar_x + bar_w + photo_gap,
                                    bar_y + bar_h - photo.height))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def slugify(text):
    keep = []
    for ch in str(text or "player"):
        keep.append(ch if ch.isalnum() else "_")
    slug = "".join(keep).strip("_").lower()
    return slug or "player"
