"""Candidate portraits: openly licensed photos in data/seed/photos/, published as small black-and-white crops.

credits.json lists, per candidate, the source file page, author and licence. Only public-domain or Creative
Commons images belong there; a CC licence needs the credit line the profile page prints under the photo,
and "converted to black and white, cropped" is that line's note of the change.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageOps

from . import config

PHOTO_DIR = config.SEED_DIR / "photos"
SIZE = (300, 400)  # 3:4 portrait


def load_credits() -> dict[str, dict]:
    path = PHOTO_DIR / "credits.json"
    return json.loads(path.read_text()) if path.exists() else {}


def portrait(src: Path, dest: Path) -> None:
    """Crop to 3:4 (keeping the top of a tall photo, where the face is), shrink, and save in black and white."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        w, h = im.size
        target = SIZE[0] / SIZE[1]
        if w / h > target:  # too wide: trim the sides evenly
            cw = round(h * target)
            box = ((w - cw) // 2, 0, (w - cw) // 2 + cw, h)
        else:  # too tall: keep the top, with a little headroom
            ch = round(w / target)
            top = min(round((h - ch) * 0.15), h - ch)
            box = (0, top, w, top + ch)
        im = ImageOps.autocontrast(im.crop(box).resize(SIZE, Image.LANCZOS), cutoff=0.5)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=82, optimize=True, progressive=True)


def credit_line(c: dict) -> str:
    """'Photo: Gage Skidmore, CC BY-SA 4.0' or 'Photo: U.S. Senate (public domain)'."""
    if c["license"].lower().startswith("public domain"):
        return f"Photo: {c['author']} (public domain)"
    return f"Photo: {c['author']}, {c['license']}"


def build(dist: Path) -> dict[str, dict]:
    """Write every portrait to dist/static/img/candidates/ and return candidate name -> photo context."""
    out = {}
    for name, c in load_credits().items():
        src = PHOTO_DIR / c["file"]
        if not src.exists():
            continue
        rel = f"/static/img/candidates/{c['slug']}.jpg"
        portrait(src, dist / rel.lstrip("/"))
        out[name] = dict(src=rel, width=SIZE[0], height=SIZE[1], credit=credit_line(c), source=c["source"],
                         license=c["license"], license_url=c.get("license_url"), note="Converted to black and white and cropped.")
    return out
