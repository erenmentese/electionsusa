"""Open Graph share images (1200x630), rendered at build time.

Reuses the bot's 1600x900 card renderer and centres it on a 1.91:1 canvas, so
Facebook, LinkedIn and X show the whole card instead of cropping its top and
bottom. One image per race with the current average, plus a site-wide card.
"""
from __future__ import annotations

import io
from datetime import date

from PIL import Image, ImageDraw

from . import average, config
from .social_cards import BLUE, PAPER, RED, CardSpec, Figure, render
from .social_compose import margin_label, race_title, short

OG_W, OG_H = 1200, 630


def pct(v: float) -> str:
    # always one decimal, like the site, so "11.0%" sits next to "14.7%" rather than "11%"
    return f"{v:.1f}%"


def to_og(png: bytes) -> bytes:
    card = Image.open(io.BytesIO(png))
    card = card.resize((round(card.width * OG_H / card.height), OG_H), Image.LANCZOS)
    canvas = Image.new("RGB", (OG_W, OG_H), PAPER)
    canvas.paste(card, ((OG_W - card.width) // 2, 0))
    d = ImageDraw.Draw(canvas)
    # the scaled card's ribbon stops short of the side margins; redraw it full width
    d.rectangle([0, 0, OG_W // 2, 5], fill=BLUE)
    d.rectangle([OG_W // 2, 0, OG_W, 5], fill=RED)
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def ranked(ra: average.RaceAverage) -> list[str]:
    return sorted((c for c in ra.values if c != "Other/Undecided"), key=lambda c: -ra.values[c])


def headline(race: config.Race, ra: average.RaceAverage) -> tuple[str, str]:
    """(value, note) summarising a race in a few characters, e.g. ("Newsom +1.2", "")."""
    if race.kind == "approval":
        return pct(ra.values["Approve"]), "approve"
    if race.kind == "primary":
        lead = ranked(ra)[0]
        return f"{short(lead)} {pct(ra.values[lead])}", "leads"
    return margin_label(ra.margin, race.candidates[0], race.candidates[1]), ""


def race_card(race: config.Race, ra: average.RaceAverage, colors: dict[str, str], as_of: date) -> CardSpec:
    order = ranked(ra)[:4] if race.kind == "primary" else [c for c in race.candidates if c in ra.values]
    if race.kind == "approval" and ra.margin is not None:
        lead = f"Net {ra.margin:+.1f}".replace("-", "−")
    elif race.kind == "primary":
        lead = f"{short(order[0])} leads"
    else:
        lead = margin_label(ra.margin, race.candidates[0], race.candidates[1])
    polls = f"weighted average of {ra.n_polls} poll{'s' if ra.n_polls != 1 else ''}"
    return CardSpec(kind="figures", kicker=f"Polling average · {as_of.strftime('%B %-d, %Y')}", title=race_title(race),
                    figures=[Figure(short(c), pct(ra.values[c]), colors.get(c, "#0e0e0f")) for c in order],
                    note=f"{lead} · {polls}" if lead else polls.capitalize(),
                    footer_left="Every poll linked to its source")


def site_card(summaries: list[dict], as_of: date) -> CardSpec:
    rows = [(s["race"].short_title, *headline(s["race"], s["avg"])) for s in summaries
            if s["race"].featured and s["avg"].values]
    return CardSpec(kind="list", kicker=f"Polling averages · {as_of.strftime('%B %-d, %Y')}", title="How is 2028 looking?",
                    rows=rows, footer_left="Free, open data · every poll linked to its source")


def race_image(race: config.Race, ra: average.RaceAverage, colors: dict[str, str], as_of: date) -> bytes:
    return to_og(render(race_card(race, ra, colors, as_of)))


def site_image(summaries: list[dict], as_of: date) -> bytes:
    return to_og(render(site_card(summaries, as_of)))
