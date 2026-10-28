"""1600x900 PNG share cards in the site's visual language (Pillow only).

Paper background, blue/red ribbon, Instrument Serif numerals over a coloured
rule, Inter for labels. Fonts are bundled in assets/fonts (SIL OFL).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from . import config

W, H = 1600, 900
PAD = 96
PAPER = "#fbfbf9"
INK = "#0e0e0f"
INK2 = "#3a3a3c"
MUTE = "#77777a"
RULE = "#e4e3de"
BLUE = "#1d3f8f"
RED = "#b3262e"
FONT_DIR = config.ROOT / "assets" / "fonts"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def serif(size: int):
    return _font("InstrumentSerif-Regular.ttf", size)


def sans(size: int, weight: str = "Regular"):
    return _font(f"Inter-{weight}.ttf", size)


@dataclass
class Figure:
    label: str
    value: str
    color: str = INK


@dataclass
class CardSpec:
    kind: str                      # figures | list | countdown
    kicker: str
    title: str
    figures: list[Figure] = field(default_factory=list)
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # (label, value, note)
    big: str = ""
    big_unit: str = ""
    note: str = ""                 # line under the figures
    footer_left: str = ""


def _tracked(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking: float = 0.1):
    x, y = xy
    size = font.size
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking * size
    return x


def _fit_font(draw, text: str, maker, start: int, max_w: int, min_size: int = 40):
    size = start
    while size > min_size and draw.textlength(text, font=maker(size)) > max_w:
        size -= 4
    return maker(size)


def _frame(spec: CardSpec) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W // 2, 8], fill=BLUE)
    d.rectangle([W // 2, 0, W, 8], fill=RED)
    _tracked(d, (PAD, 74), spec.kicker.upper(), sans(24, "SemiBold"), MUTE, 0.12)
    tf = _fit_font(d, spec.title, serif, 92, W - 2 * PAD)
    d.text((PAD, 112), spec.title, font=tf, fill=INK)
    # footer
    fy = H - 112
    d.line([PAD, fy, W - PAD, fy], fill=INK, width=2)
    if spec.footer_left:
        ff = _fit_font(d, spec.footer_left, lambda s: sans(s), 28, W - 2 * PAD - 420, 20)
        d.text((PAD, fy + 30), spec.footer_left, font=ff, fill=INK2)
    brand = "electionsusa.org"
    bf = sans(30, "SemiBold")
    d.text((W - PAD - d.textlength(brand, font=bf), fy + 28), brand, font=bf, fill=INK)
    handle = config.BOT.get("handle")
    if handle:
        hf = sans(22)
        d.text((W - PAD - d.textlength(handle, font=hf), fy + 66), handle, font=hf, fill=MUTE)
    return img, d


def _figures(d: ImageDraw.ImageDraw, spec: CardSpec):
    figs = spec.figures[:4]
    if not figs:
        return
    gap = 56
    col_w = (W - 2 * PAD - gap * (len(figs) - 1)) / len(figs)
    top = 300
    for i, f in enumerate(figs):
        x = PAD + i * (col_w + gap)
        lf = _fit_font(d, f.label, lambda s: sans(s, "SemiBold"), 30, int(col_w), 18)
        d.text((x, top), f.label, font=lf, fill=MUTE)
        d.rectangle([x, top + 50, x + min(col_w, 300), top + 58], fill=f.color)
        vsize = 220 if len(figs) <= 2 else 180 if len(figs) == 3 else 150
        vf = _fit_font(d, f.value, serif, vsize, int(col_w), 80)
        d.text((x - 4, top + 62), f.value, font=vf, fill=INK)
    if spec.note:
        nf = _fit_font(d, spec.note, lambda s: sans(s), 32, W - 2 * PAD, 20)
        d.text((PAD, H - 186), spec.note, font=nf, fill=INK2)


def _list(d: ImageDraw.ImageDraw, spec: CardSpec):
    rows = spec.rows[:5]
    top, row_h = 262, 88
    lf, vf, nf = sans(32, "SemiBold"), serif(70), sans(26)
    for i, (label, value, note) in enumerate(rows):
        y = top + i * row_h
        d.line([PAD, y + row_h - 6, W - PAD, y + row_h - 6], fill=RULE, width=2)
        d.text((PAD, y + 28), label, font=lf, fill=INK)
        vw = d.textlength(value, font=vf)
        nw = d.textlength(note, font=nf) if note else 0
        d.text((W - PAD - vw - (nw + 28 if note else 0), y + 2), value, font=vf, fill=INK)
        if note:
            d.text((W - PAD - nw, y + 34), note, font=nf, fill=MUTE)


def _countdown(d: ImageDraw.ImageDraw, spec: CardSpec):
    bf = serif(400)
    d.text((PAD - 12, 196), spec.big, font=bf, fill=INK)
    bw = d.textlength(spec.big, font=bf)
    d.text((PAD + bw + 24, 470), spec.big_unit, font=sans(56, "SemiBold"), fill=MUTE)
    if spec.note:
        nf = _fit_font(d, spec.note, lambda s: sans(s), 34, W - 2 * PAD, 20)
        d.text((PAD, H - 196), spec.note, font=nf, fill=INK2)


def render(spec: CardSpec) -> bytes:
    img, d = _frame(spec)
    {"figures": _figures, "list": _list, "countdown": _countdown}[spec.kind](d, spec)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
