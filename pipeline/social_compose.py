"""Decide what the bot should post, given the data and what it already posted.

Three kinds of post, each with a share card:
  * poll       - a newly released poll, with the effect on our average
  * roundup    - weekly summary of every average with the 7-day change
  * milestone  - countdown milestones for the 2026 midterms and 2028 election

Deduplication lives in data/bot_state.json, which the workflow commits back.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import average, config
from .schema import validate_polls
from .social_cards import CardSpec, Figure
from .social_text import fit_lines

STATE_PATH = config.DATA_DIR / "bot_state.json"
POP = {"LV": "likely voters", "RV": "registered voters", "A": "adults"}
PARTY_TAG = {"DEM": "D", "REP": "R"}
PRIORITY = {"milestone": 0, "roundup": 1, "general": 2, "primary": 2, "approval": 3, "generic": 4}


@dataclass
class Post:
    kind: str
    key: str                       # dedupe key stored in state
    text: str
    card: CardSpec | None = None
    alt: str = ""
    priority: int = 5
    meta: dict = field(default_factory=dict)


# ------------------------------------------------------------------ state
def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    return json.loads(STATE_PATH.read_text())


def empty_state() -> dict:
    return {"posted": {}, "log": []}


def save_state(state: dict) -> None:
    state["log"] = state.get("log", [])[-300:]
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")


def posts_in_last_day(state: dict, now: datetime) -> int:
    cutoff = now - timedelta(hours=24)
    return sum(1 for e in state.get("log", []) if datetime.fromisoformat(e["ts"]) >= cutoff and e.get("live"))


# ------------------------------------------------------------------ helpers
def short(c: str) -> str:
    if c in ("Approve", "Disapprove", "Democrats", "Republicans", "Other/Undecided"):
        return c
    words = [w for w in c.split() if w.rstrip(".") not in ("Jr", "Sr", "II", "III")]
    return words[-1] if words else c


def fmt_pct(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".") + "%"


def fmt_dates(start: date, end: date) -> str:
    if start == end or pd.isna(start):
        return end.strftime("%b %-d")
    if start.month == end.month:
        return f"{start.strftime('%b')} {start.day}–{end.day}"
    return f"{start.strftime('%b %-d')} – {end.strftime('%b %-d')}"


def margin_label(m: float | None, a: str, b: str) -> str:
    if m is None:
        return ""
    if abs(m) < 0.05:
        return "Tied"
    return f"{short(a) if m > 0 else short(b)} +{abs(m):.1f}"


def delta(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return ""
    d = now - before
    if abs(d) < 0.05:
        return "no change"
    return f"{'▲' if d > 0 else '▼'}{abs(d):.1f}"


def race_title(race: config.Race) -> str:
    return race.short_title if race.kind != "primary" else race.title.replace(" Polls", "").replace("Primary", "primary")


def tail_lines() -> list[str]:
    extra = []
    if config.BOT.get("include_links"):
        extra.append(config.SITE["url"].replace("https://", ""))
    if config.BOT.get("hashtags"):
        extra.append(" ".join(config.BOT["hashtags"][:2]))
    return extra


# ------------------------------------------------------------------ poll posts
def poll_post(pid: str, polls: pd.DataFrame, ratings, today: date) -> Post | None:
    g = polls[polls["poll_id"] == pid]
    race = config.RACE_BY_ID.get(g["race_id"].iat[0])
    if race is None:
        return None
    vals = {c: float(v) for c, v in zip(g["candidate"], g["pct"])}
    pollster = g["pollster"].iat[0]
    start, end = g["start_date"].iat[0], g["end_date"].iat[0]
    n, pop = g["sample_size"].iat[0], g["population"].iat[0]

    now = average.compute_race(polls, race, ratings, as_of=today, trend_step_days=30)
    before = average.compute_race(polls[polls["poll_id"] != pid], race, ratings, as_of=today, trend_step_days=30)

    if race.kind == "primary":
        order = sorted((c for c in vals if c != "Other/Undecided"), key=lambda c: -vals[c])[:5]
        header = f"New poll: {race_title(race)}"
    else:
        order = [c for c in race.candidates if c in vals]
        header = f"New poll: {race_title(race)}" if race.kind != "general" else f"New 2028 poll: {race.short_title}"
    if len(order) < 1:
        return None

    def label(c: str) -> str:
        p = PARTY_TAG.get(race.parties.get(c, ""))
        return f"{short(c)} ({p})" if p and race.kind == "general" else short(c)

    lines = [header, ""] + [f"{label(c)} {fmt_pct(vals[c])}" for c in order]
    if race.kind in ("general", "generic", "approval") and len(order) >= 2:
        m = vals[order[0]] - vals[order[1]]
        lines.append(f"Net {m:+.0f}".replace("-", "−") if race.kind == "approval" else margin_label(m, order[0], order[1]))

    sample = []
    if pd.notna(n):
        sample.append(f"{int(n):,}")
    if pop in POP:
        sample.append(POP[pop])
    who = " · ".join(x for x in [pollster, fmt_dates(start, end), " ".join(sample)] if x)
    lines += ["", who]

    avg_line = ""
    if now.values:
        if race.kind == "primary":
            lead = max(now.values, key=now.values.get)
            avg_line = f"Our average: {short(lead)} leads at {now.values[lead]:.1f}%"
            d = delta(now.values.get(lead), before.values.get(lead) if before.values else None)
        elif race.kind == "approval":
            ap = now.values.get("Approve")
            avg_line = f"Our average: {ap:.1f}% approve" if ap is not None else "Our average:"
            d = delta(ap, before.values.get("Approve") if before.values else None)
        else:
            avg_line = "Our average: " + margin_label(now.margin, race.candidates[0], race.candidates[1])
            d = delta(now.margin, before.margin)
        if not before.values:
            avg_line += " (only recent poll)"
        elif d:
            avg_line += f" ({d} with this poll)"
        lines.append(avg_line)
    lines += tail_lines()
    text = fit_lines(lines, optional_from=len(lines) - len(tail_lines()) - 1)

    colors = {c: config.PARTY_COLORS.get(race.parties.get(c, "OTHER"), INK_FALLBACK) for c in order}
    if race.kind == "primary":
        pal = ["#1e3a8a", "#0f766e", "#5b21b6", "#9f1239"] if race.id.startswith("dem") else ["#991b1b", "#9a3412", "#854d0e", "#5b21b6"]
        colors = {c: pal[i % len(pal)] for i, c in enumerate(order)}
    card = CardSpec(kind="figures", kicker=f"New poll · {race_title(race)}", title=pollster,
                    figures=[Figure(short(c), fmt_pct(vals[c]), colors[c]) for c in order[:4]],
                    note=avg_line, footer_left=" · ".join(x for x in [fmt_dates(start, end) + f", {end.year}", " ".join(sample)] if x))
    alt = f"{pollster} poll, {race_title(race)}: " + ", ".join(f"{c} {fmt_pct(vals[c])}" for c in order) + f". Fieldwork {fmt_dates(start, end)}, {end.year}."
    return Post(kind="poll", key=f"poll:{pid}", text=text, card=card, alt=alt,
                priority=PRIORITY.get(race.kind, 5), meta={"race": race.id, "end": end.isoformat()})


INK_FALLBACK = "#0e0e0f"


# ------------------------------------------------------------------ roundup
def roundup_post(polls: pd.DataFrame, ratings, today: date) -> Post | None:
    rows, lines = [], [f"The week in polls ({today.strftime('%b %-d')})", ""]
    for rid in ("approval-trump-2", "generic-ballot-2026", "pres-2028-vance-newsom", "dem-primary-2028", "gop-primary-2028"):
        race = config.RACE_BY_ID[rid]
        now = average.compute_race(polls, race, ratings, as_of=today, trend_step_days=30)
        prev = average.compute_race(polls, race, ratings, as_of=today - timedelta(days=7), trend_step_days=30)
        if not now.values:
            continue
        if race.kind == "approval":
            v = now.values.get("Approve")
            val, d = f"{v:.1f}%", delta(v, prev.values.get("Approve") if prev.values else None)
            label = "Trump approval"
        elif race.kind == "primary":
            lead = max((c for c in now.values if c != "Other/Undecided"), key=now.values.get)
            val = f"{short(lead)} {now.values[lead]:.1f}%"
            d = delta(now.values[lead], prev.values.get(lead) if prev.values else None)
            label = "Dem primary" if rid.startswith("dem") else "GOP primary"
        else:
            val = margin_label(now.margin, race.candidates[0], race.candidates[1])
            d = delta(now.margin, prev.margin)
            label = race.short_title
        rows.append((label, val, d if d and d != "no change" else ""))
        lines.append(f"{label}: {val}" + (f" ({d})" if d and d != "no change" else ""))
    if not rows:
        return None
    days = (config.ELECTION_DAY_2028 - today).days
    lines += ["", f"{days} days to Election Day 2028."] + tail_lines()
    text = fit_lines(lines, optional_from=len(lines) - len(tail_lines()))
    card = CardSpec(kind="list", kicker=f"Weekly roundup · {today.strftime('%B %-d, %Y')}", title="The week in polls",
                    rows=rows, footer_left="Polling averages · change over the past 7 days" if any(n for _, _, n in rows)
                    else f"Polling averages as of {today.strftime('%b %-d, %Y')}")
    alt = "Weekly polling roundup. " + "; ".join(f"{l}: {v}" + (f" ({n})" if n else "") for l, v, n in rows) + "."
    return Post(kind="roundup", key=f"roundup:{today.isoformat()}", text=text, card=card, alt=alt, priority=PRIORITY["roundup"])


# ------------------------------------------------------------------ milestones
def milestone_posts(today: date) -> list[Post]:
    out = []
    d28 = (config.ELECTION_DAY_2028 - today).days
    if d28 in config.BOT["election_milestones"]:
        if d28 == 0:
            text, big, unit = "Today is Election Day 2028. Polls close on a rolling schedule from 6pm ET; results come from state election officials.", "0", "days"
        else:
            text = f"{d28} days until the 2028 presidential election.\n\nElection Day is Tuesday, November 7, 2028."
            big, unit = str(d28), "day" if d28 == 1 else "days"
        out.append(Post(kind="milestone", key=f"milestone:2028:{d28}", text=fit_lines([text] + tail_lines()),
                        card=CardSpec(kind="countdown", kicker="Countdown", title="2028 presidential election", big=big, big_unit=unit,
                                      note="Election Day: Tuesday, November 7, 2028", footer_left="Live countdown on the site"),
                        alt=f"{d28} days until the 2028 presidential election on November 7, 2028.", priority=0))
    dmid = (config.MIDTERM_DAY_2026 - today).days
    if dmid in config.BOT["midterm_milestones"]:
        text = ("Today is the 2026 midterm election." if dmid == 0 else
                f"{dmid} day{'s' if dmid != 1 else ''} until the 2026 midterm elections on Tuesday, November 3.") + \
               "\n\nAll 435 House seats, 35 Senate seats and 36 governorships are on the ballot."
        out.append(Post(kind="milestone", key=f"milestone:2026:{dmid}", text=fit_lines([text] + tail_lines()),
                        card=CardSpec(kind="countdown", kicker="Countdown", title="2026 midterm elections", big=str(dmid),
                                      big_unit="day" if dmid == 1 else "days", note="Election Day: Tuesday, November 3, 2026",
                                      footer_left="House · Senate · Governors"),
                        alt=f"{dmid} days until the 2026 midterm elections on November 3, 2026.", priority=0))
    return out


# ------------------------------------------------------------------ plan
def plan(polls: pd.DataFrame, ratings, state: dict, today: date, now: datetime | None = None) -> list[Post]:
    """Return the posts to publish this run, highest priority first, within caps."""
    now = now or datetime.now(timezone.utc)
    polls = validate_polls(polls)
    posted = state.get("posted", {})
    candidates: list[Post] = []

    candidates += [p for p in milestone_posts(today) if p.key not in posted]

    if today.weekday() == config.BOT["roundup_weekday"] and f"roundup:{today.isoformat()}" not in posted:
        rp = roundup_post(polls, ratings, today)
        if rp:
            candidates.append(rp)

    fresh_cut = today - timedelta(days=config.BOT["fresh_days"])
    for pid, g in polls.groupby("poll_id"):
        if f"poll:{pid}" in posted:
            continue
        if g["end_date"].iat[0] < fresh_cut or g["end_date"].iat[0] > today:
            continue
        pp = poll_post(pid, polls, ratings, today)
        if pp:
            candidates.append(pp)

    candidates.sort(key=lambda p: (p.priority, -(date.fromisoformat(p.meta["end"]).toordinal() if "end" in p.meta else 0)))
    room = max(0, config.BOT["max_posts_per_day"] - posts_in_last_day(state, now))
    return candidates[: min(config.BOT["max_posts_per_run"], room)]


def bootstrap(polls: pd.DataFrame, state: dict, now: datetime) -> int:
    """Mark every poll already in the dataset as posted, so a new account starts clean."""
    n = 0
    for pid in validate_polls(polls)["poll_id"].unique():
        key = f"poll:{pid}"
        if key not in state["posted"]:
            state["posted"][key] = now.isoformat()
            n += 1
    return n
