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


# ------------------------------------------------------------- map builder
DISTRICT_STATES = ("ME", "NE")  # one electoral vote per congressional district, two for the statewide winner


def builder_context(states: dict[str, history.StateHistory], year: int) -> dict:
    """Data for the 2028 map builder, starting from `year`.

    Each state carries its margin (R-positive) and electoral votes. Where Maine or Nebraska split in
    `year`, the district that went the other way (the 2nd, in every split so far) becomes its own unit;
    with no district results in our data it has no margin and keeps its `year` winner until tapped.
    """
    m = map_context(states, year)
    units, districts = [], []
    for st in states.values():
        y = st.by_year(year)
        ev = y.ev
        if st.po in DISTRICT_STATES and y.ev_dem and y.ev_rep:
            ev -= 1
            districts.append(dict(po=f"{st.po}2", n=f"{st.name}'s 2nd district", ev=1, m=None,
                                  w="D" if y.ev_dem < y.ev_rep else "R", u=st.path))
        units.append(dict(po=st.po, n=st.name, ev=ev, m=round(y.margin, 2), u=st.path))
    below = BOX_Y + len(BOXED) * (BOX_SIZE + BOX_GAP) + 12
    boxes = m["boxes"] + [dict(po=d["po"], path=d["u"], cls="r2" if d["w"] == "R" else "d2", label=f"{d['po'][:2]}-2",
                               x=BOX_X, y=below + i * (BOX_SIZE + BOX_GAP), size=BOX_SIZE)
                          for i, d in enumerate(districts)]
    return dict(m, boxes=boxes, units=units + districts)


def tipping_point(units: list[dict], party: str) -> tuple[dict, float] | None:
    """The unit that would give `party` its 270th electoral vote under a uniform swing, and that swing in points."""
    sign = 1 if party == "D" else -1  # Democrats gain as margins fall
    total = sum(u["ev"] for u in units if u["m"] is None and u["w"] == party)
    for u in sorted((u for u in units if u["m"] is not None), key=lambda u: sign * u["m"]):
        total += u["ev"]
        if total >= 270:
            return u, sign * u["m"]
    return None
