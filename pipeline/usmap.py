"""U.S. state outlines as inline SVG, shaded by result and linked to each state's page.

Geometry: us-atlas states-albers-10m (ISC), built from Census cartographic boundaries and
already projected to Albers USA in a 975x610 frame with Alaska and Hawaii inset. This module
only decodes the TopoJSON arcs and writes compact relative paths with integer coordinates
(~1px at full width), which keeps the whole map around 40 KB before gzip.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import config, history

TOPO = config.SEED_DIR / "us-atlas" / "states-albers-10m.json"
W, H = 975, 610

# States too small to tap on the map get a labelled box in the Atlantic, east of the coast
BOXED = ["VT", "NH", "MA", "RI", "CT", "NJ", "DE", "MD", "DC"]
BOX_X, BOX_Y, BOX_SIZE, BOX_GAP = 915, 205, 18, 9  # clear of Long Island (x<=903) and Rhode Island (y<=196)


@lru_cache(maxsize=1)
def state_paths() -> dict[str, str]:
    """FIPS code -> SVG path data."""
    topo = json.loads(TOPO.read_text())
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:  # delta-encoded, quantized
        x = y = 0
        pts = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append((round(x * sx + tx), round(y * sy + ty)))
        arcs.append(pts)

    def ring(indices: list[int]) -> list[tuple[int, int]]:
        pts: list[tuple[int, int]] = []
        for i in indices:
            seg = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(seg if not pts else seg[1:])
        return [p for k, p in enumerate(pts) if k == 0 or p != pts[k - 1]]

    out = {}
    for geom in topo["objects"]["states"]["geometries"]:
        polygons = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        d = []
        for polygon in polygons:
            for r in polygon:
                pts = ring(r)
                if len(pts) < 4:  # islands that collapse to a point at this precision
                    continue
                steps = " ".join(f"{x1 - x0},{y1 - y0}" for (x0, y0), (x1, y1) in zip(pts, pts[1:]))
                d.append(f"M{pts[0][0]},{pts[0][1]}l{steps}z")
        out[geom["id"]] = "".join(d)
    return out


def shade(margin: float) -> str:
    """CSS class for a margin: d1/r1 under 5 points, d2/r2 under 15, d3/r3 beyond."""
    level = 1 if abs(margin) < 5 else 2 if abs(margin) < 15 else 3
    return f"{'r' if margin > 0 else 'd'}{level}"


def map_context(states: dict[str, history.StateHistory], year: int) -> dict:
    """Everything the us_map macro draws: shaded, linked states plus boxes for the small ones."""
    paths = state_paths()
    shapes, boxes = [], []
    for st in states.values():
        y = st.by_year(year)
        summary = f"{st.name}: {y.margin_label} · {y.ev} electoral votes"
        item = dict(path=st.path, cls=shade(y.margin), summary=summary, po=st.po)
        shapes.append(dict(item, d=paths[st.fips]))
        if st.po in BOXED:
            i = BOXED.index(st.po)
            boxes.append(dict(item, x=BOX_X, y=BOX_Y + i * (BOX_SIZE + BOX_GAP), size=BOX_SIZE))
    boxes.sort(key=lambda b: b["y"])
    return dict(shapes=shapes, boxes=boxes, width=W, height=H, year=year,
                label=f"Map of the {year} presidential election result in each state")


def ev_bar(n: history.NationYear) -> dict:
    return dict(dem=history.short(n.dem), rep=history.short(n.rep), ev_dem=n.ev_dem, ev_rep=n.ev_rep,
                dem_w=round(100 * n.ev_dem / 538, 2), rep_w=round(100 * n.ev_rep / 538, 2))
