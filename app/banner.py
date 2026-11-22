"""Broadcast name-banner (bug) renderer.

Draws a transparent full-resolution canvas with the name bug positioned
bottom-left, so the PNG can be dropped straight into OBS / vMix /
ATEM as a media source keyed over the live picture.

All geometry scales from the frame height, so one renderer serves
720p through 4K broadcasts.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
BOLD_FONT = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
REG_FONT = os.path.join(FONT_DIR, "DejaVuSans.ttf")

DEFAULT_ACCENT = "#E4392B"
DEFAULT_BAR = "#0C101C"
TEXT_COLOR = "#FFFFFF"
BAR_ALPHA = 232


def _font(path, size):
    return ImageFont.truetype(path, max(8, int(size)))


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
    pad = round(bar_h * 0.35)
    radius = round(bar_h * 0.18)

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

    # Rounded bar with an accent strip along the bottom edge, both clipped
    # to the bar's rounding.
    bar = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar)
    bar_draw.rounded_rectangle([0, 0, bar_w - 1, bar_h - 1], radius=radius,
                               fill=(*bar_rgb, BAR_ALPHA))
    strip_h = max(2, round(bar_h * 0.10))
    mask = Image.new("L", (bar_w, bar_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, bar_w - 1, bar_h - 1],
                                           radius=radius, fill=255)
    accent_layer = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
    ImageDraw.Draw(accent_layer).rectangle([0, bar_h - strip_h, bar_w, bar_h],
                                           fill=(*accent_rgb, 255))
    accent_layer.putalpha(Image.composite(accent_layer.split()[3],
                                          Image.new("L", (bar_w, bar_h), 0), mask))
    bar.alpha_composite(accent_layer)
    canvas.alpha_composite(bar, dest=(bar_x, bar_y))

    draw = ImageDraw.Draw(canvas)
    cursor = bar_x + pad

    if logo is not None:
        _paste_rgba(canvas, logo, (cursor, bar_y + (bar_h - logo.height) // 2))
        cursor += logo_w + pad

    if chip_w:
        chip = Image.new("RGBA", (chip_w, bar_h), (0, 0, 0, 0))
        chip_draw = ImageDraw.Draw(chip)
        chip_draw.rounded_rectangle([0, 0, chip_w - 1, bar_h - 1], radius=radius,
                                    fill=(*accent_rgb, 255))
        num_font = _font(BOLD_FONT, bar_h * 0.55)
        num_text = str(number)
        bb = chip_draw.textbbox((0, 0), num_text, font=num_font)
        chip_draw.text(((chip_w - (bb[2] - bb[0])) / 2 - bb[0],
                        (bar_h - (bb[3] - bb[1])) / 2 - bb[1]),
                       num_text, font=num_font, fill=TEXT_COLOR)
        canvas.alpha_composite(chip, dest=(cursor, bar_y))
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
