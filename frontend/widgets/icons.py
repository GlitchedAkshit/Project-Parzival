"""
Crisp monochrome icons rendered from Windows' built-in "Segoe MDL2 Assets"
icon font into CTkImages, so there are no image files to ship. A Tk widget
can only use one font, which is why the glyph is rendered to an image
rather than mixed into the button text. Returns None (no icon) if Pillow or
the font isn't available, and callers simply show text instead.
"""

import os

import customtkinter as ctk

_FONT_PATH = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segmdl2.ttf")
_cache = {}


def icon(glyph, color, size=18):
    key = (glyph, color, size)
    if key in _cache:
        return _cache[key]

    image = None
    try:
        from PIL import Image, ImageDraw, ImageFont

        scale = 3   # render large, let CTkImage scale down -> sharp at any DPI
        px = size * scale
        font = ImageFont.truetype(_FONT_PATH, int(px * 0.85))
        img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
        draw.text(((px - (right - left)) / 2 - left, (px - (bottom - top)) / 2 - top),
                  glyph, font=font, fill=color)
        image = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    except Exception as e:
        print(f"[icons] Icon unavailable ({e}) - falling back to text")

    _cache[key] = image
    return image
