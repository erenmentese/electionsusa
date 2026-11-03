"""Build the static site into dist/.

    python -m pipeline.build            # uses data/*.csv, writes dist/
    python -m pipeline.build --as-of 2026-10-25

No network access is needed. Everything the templates show is computed here so
the HTML is complete without JavaScript (JS only animates the countdown).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import accuracy, average, charts, check_data, config, dedupe, fetch_markets, history, og_cards, pollsters, scorecard, usmap
from .schema import MARKET_COLUMNS, POLL_COLUMNS, validate_polls

# One nav on every page: the main sections, then a "More" menu
NAV = [
    ("Approval", "/approval/trump/"),
    ("2028 President", "/2028/president/"),
    ("2028 Map", "/2028/map/"),
    ("States", "/states/"),
    ("Pollsters", "/pollsters/"),
]
NAV_MORE = [
    ("Dem Primary", "/2028/democratic-primary/"),
    ("GOP Primary", "/2028/republican-primary/"),
    ("2028 Calendar", "/2028/calendar/"),
    ("Markets", "/markets/"),
    ("Data & API", "/data/"),
    ("Countdown", "/countdown/"),
]


MIDTERM_NAV = ("2026 Midterms", "/2026/")


def nav_items(as_of: date) -> list[tuple[str, str]]:
    """The primary nav; the 2026 hub leads it from a week before the midterms to six weeks after."""
    return [MIDTERM_NAV, *NAV] if -42 <= (config.MIDTERM_DAY_2026 - as_of).days <= 7 else NAV


# ----------------------------------------------------------------- helpers
def fmt_dates(start, end) -> str:
    if pd.isna(end):
        return ""
    if pd.isna(start) or start == end:
        return end.strftime("%b %-d, %Y")
    if start.month == end.month and start.year == end.year:
        return f"{start.strftime('%b')} {start.day}–{end.day}, {end.year}"
    if start.year == end.year:
        return f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"
    return f"{start.strftime('%b %-d, %Y')} – {end.strftime('%b %-d, %Y')}"


def fmt_sample(n, pop) -> str:
    parts = []
    if pd.notna(n):
        parts.append(f"{int(n):,}")
    if pop:
        parts.append(pop)
    return " ".join(parts) or "—"


def signed(x: float | None, plus_label: str = "", minus_label: str = "") -> str:
    if x is None:
        return "—"
    if abs(x) < 0.05:
        return "Tie"
    lab = plus_label if x > 0 else minus_label
    return f"{lab} +{abs(x):.1f}".strip()


SUFFIXES = {"Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV"}


def short_name(c: str) -> str:
    """Surname for tables and legends; a generational suffix stays with it ("Trump Jr.", not "Jr.")."""
    if c in ("Other/Undecided", "Approve", "Disapprove", "Democrats", "Republicans"):
        return c
    words = c.replace(",", "").split()
    if len(words) > 1 and words[-1] in SUFFIXES:
        return f"{words[-2]} {words[-1]}"
    return words[-1]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    polls_path = config.DATA_DIR / "polls.csv"
    # one row set per real poll: copies and secondary populations never reach an average (see dedupe)
    polls = dedupe.collapse(validate_polls(pd.read_csv(polls_path))) if polls_path.exists() else pd.DataFrame(columns=POLL_COLUMNS)
    mpath = config.DATA_DIR / "markets.csv"
    markets = pd.read_csv(mpath) if mpath.exists() else pd.DataFrame(columns=MARKET_COLUMNS)
    _, ratings = scorecard.load_538()
    return polls, markets, ratings


def race_table(ra: average.RaceAverage, race: config.Race, ratings: pd.DataFrame, pollster_path=lambda p, s: None) -> list[dict]:
    wide = ra.polls
    if wide is None or wide.empty:
        return []
    grades = average._grade_lookup(ratings)
    w = average.poll_weights(wide, ra.as_of, race.half_life_days, grades)
    w = (100 * w / w.sum()) if w.sum() > 0 else w
    rows = []
    for i, r in wide.iterrows():
        vals = {c: (None if pd.isna(r[c]) else float(r[c])) for c in race.candidates}
        margin = None
        if len(race.candidates) >= 2 and vals.get(race.candidates[0]) is not None and vals.get(race.candidates[1]) is not None:
            margin = vals[race.candidates[0]] - vals[race.candidates[1]]
        sponsor = r["sponsor"] if isinstance(r["sponsor"], str) else ""
        rows.append(dict(
            pollster=r["pollster"], sponsor=sponsor, pollster_path=pollster_path(r["pollster"], sponsor),
            dates=fmt_dates(r["start_date"], r["end_date"]), end_date=r["end_date"].isoformat(),
            sample=fmt_sample(r["sample_size"], r["population"]),
            grade=average.pollster_grade(r["pollster"], sponsor, grades) or "—",
            weight=round(float(w.loc[i]), 1) if len(w) else 0.0,
            vals=vals, margin=margin,
            margin_label=signed(margin, short_name(race.candidates[0]), short_name(race.candidates[1])) if margin is not None else "—",
            source_url=r["source_url"] if isinstance(r["source_url"], str) else "",
            notes=r["notes"] if isinstance(r["notes"], str) else "",
        ))
    return rows


def race_colors(race: config.Race) -> dict[str, str]:
    return {c: config.PARTY_COLORS.get(race.parties.get(c, "OTHER"), "#6b7280") for c in race.candidates}


def primary_colors(race: config.Race, top: list[str]) -> dict[str, str]:
    # distinct shades for same-party candidates
    palette = ["#1e3a8a", "#0f766e", "#5b21b6", "#9f1239", "#9a3412", "#52525b"] if race.parties.get(top[0] if top else "", "DEM") == "DEM" \
        else ["#991b1b", "#9a3412", "#854d0e", "#5b21b6", "#0f766e", "#52525b"]
    return {c: palette[i % len(palette)] for i, c in enumerate(top)}


def answer_sentence(race: config.Race, ra: average.RaceAverage, as_of: date) -> str:
    """One quotable, dated sentence with the current average: the page lead and its meta description."""
    v = ra.values
    if not v:
        return ""
    national = "national " if race.kind == "primary" else ""
    src = f"the ElectionsUSA average of {ra.n_polls} {national}poll{'s' if ra.n_polls != 1 else ''}"
    when = f"as of {as_of.strftime('%B %-d, %Y')}"
    if race.kind == "approval":
        who = race.short_title.removesuffix(" approval")
        if "Disapprove" not in v:
            return f"{who}'s job approval stands at {v['Approve']:.1f}% in {src}, {when}."
        net = f"{v['Approve'] - v['Disapprove']:+.1f}".replace("-", "−")
        return f"{who}'s job approval stands at {v['Approve']:.1f}% approve and {v['Disapprove']:.1f}% disapprove (net {net}) in {src}, {when}."
    if race.kind == "primary":
        top = og_cards.ranked(ra)
        contest = race.title.removesuffix(" Polls").replace("Primary", "primary")
        if len(top) > 1 and f"{v[top[0]]:.1f}" == f"{v[top[1]]:.1f}":
            lead = f"{top[0]} and {top[1]} are tied for the lead in the {contest} at {v[top[0]]:.1f}%"
            rest = top[2:4]
        else:
            lead = f"{top[0]} leads the {contest} with {v[top[0]]:.1f}%"
            rest = top[1:3]
        behind = f", ahead of {' and '.join(f'{c} ({v[c]:.1f}%)' for c in rest)}" if rest else ""
        return f"{lead} in {src}{behind}, {when}."
    a, b = race.candidates[:2]
    if a not in v or b not in v:
        return ""
    what = "on the generic congressional ballot" if race.kind == "generic" else "in a hypothetical 2028 matchup"
    if f"{v[a]:.1f}" == f"{v[b]:.1f}":
        return f"{a} and {b} are tied at {v[a]:.1f}% {what}, according to {src}, {when}."
    lead, trail = (a, b) if v[a] > v[b] else (b, a)
    verb = "lead" if race.kind == "generic" else "leads"  # "Democrats lead", "Newsom leads"
    return f"{lead} {verb} {trail} {v[lead]:.1f}% to {v[trail]:.1f}% {what}, according to {src}, {when}."


FRESH_DAYS = 7  # "Today" in a title only while a poll has ended this recently
THIN_POLLS = 5  # fewer weighted polls than this: a "limited data" note and noindex
MAX_TABLE_ROWS = 50  # polls listed in a page's HTML; the rest are in the JSON and CSV


def seo_title(race: config.Race, ra: average.RaceAverage, as_of: date) -> str:
    """The <title>: the query people type plus the number, dated by the latest poll, e.g.
    "Trump Approval Rating Today: 37.4% (Nov 2, 2026)". "Today" only when that poll is under a week old."""
    v = ra.values
    if not v or ra.latest_end_date is None:
        return race.title
    latest = pd.Timestamp(ra.latest_end_date).date()
    when = latest.strftime("%b %-d, %Y")
    today = " Today" if (as_of - latest).days <= FRESH_DAYS else ""
    if race.kind == "approval":
        return f"{race.short_title.removesuffix(' approval')} Approval Rating{today}: {v['Approve']:.1f}% ({when})"
    if race.kind == "primary":
        lead = og_cards.ranked(ra)[0]
        return f"{race.title.removesuffix(' Polls')} Polls{today}: {short_name(lead)} {v[lead]:.1f}% ({when})"
    a, b = race.candidates[:2]
    lead = signed(ra.margin, short_name(a), short_name(b)) if ra.margin is not None else "Tie"
    if race.kind == "generic":
        if as_of >= config.MIDTERM_DAY_2026:
            return f"Final 2026 Generic Ballot Average: {lead} vs. the Result"
        return f"2026 Generic Ballot Polls{today}: {lead} ({when})"
    return f"{short_name(a)} vs. {short_name(b)} 2028 Polls{today}: {lead} ({when})"


def faq_items(race: config.Race, ra: average.RaceAverage, answer: str) -> list[tuple[str, str]]:
    """Questions and plain-text answers shown at the foot of an average page and marked up as FAQPage."""
    if not ra.values:
        return []
    first = {
        "approval": f"What is {race.short_title.removesuffix(' approval')}'s approval rating today?",
        "generic": "Who leads the generic congressional ballot?",
        "general": f"Who leads the {race.title.removeprefix('2028 Presidential Election Polls: ')} 2028 polls?",
        "primary": f"Who is leading the {race.title.removesuffix(' Polls').replace('Primary', 'primary')}?",
    }[race.kind]
    items = [(first, answer)]
    trend = ra.trend.get(race.candidates[0], [])
    month = next((v for d, v in reversed(trend) if (ra.as_of - d).days >= 30), None)
    if race.kind == "approval" and month is not None:
        change = ra.values["Approve"] - month
        items.append(("How has it changed over the last month?",
                      f"Approval is {abs(change):.1f} points {'higher' if change > 0 else 'lower'} than 30 days ago, when the average stood at {month:.1f}%."
                      if abs(change) >= 0.05 else f"It is unchanged from 30 days ago, at {month:.1f}%."))
    items += [
        ("How is this average calculated?",
         f"Every poll is weighted by how recent it is (a {race.half_life_days}-day half-life), its sample size, the pollster's track "
         "record and how often the firm publishes, so a daily tracker can't dominate. The method is fully described on the "
         "methodology page and can be reproduced from the open data."),
        ("Which polls are included?",
         f"Every public national poll we can source, {ra.n_polls_total} on record for this page and {ra.n_polls} carrying weight today. "
         "Each row in the table links to the pollster's own release; adult, registered-voter and likely-voter polls all count, but a poll released for several populations counts once (likely voters first)."),
        ("How often is it updated?",
         "Automatically, every six hours: new polls are collected, checked and added, and the average and chart are recomputed."),
        ("Can I use this data?",
         "Yes. Every poll is free to download as CSV, and every average as JSON, under CC BY 4.0. Please credit ElectionsUSA with a link."),
    ]
    return items


def faq_ld(items: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}


def related_averages(race: config.Race, averages: dict[str, average.RaceAverage]) -> list[dict]:
    """Other averages to read next, with their current number, plus the scorecard and the map."""
    out = []
    for r in config.RACES:
        ra = averages[r.id]
        if r.id == race.id or not ra.values:
            continue
        if r.kind == "primary":
            lead = og_cards.ranked(ra)[0]
            value = f"{short_name(lead)} {ra.values[lead]:.1f}%"
        elif r.kind == "approval":
            value = f"{ra.values['Approve']:.1f}% approve"
        else:
            value = signed(ra.margin, short_name(r.candidates[0]), short_name(r.candidates[1]))
        out.append(dict(title=r.short_title, path=f"/{r.slug}/", value=value))
    return out + [dict(title="Pollster scorecard", path="/pollsters/", value="Which pollsters are most accurate"),
                  dict(title="2028 electoral map", path="/2028/map/", value="Make your own forecast")]


MIDTERM_RACE = "generic-ballot-2026"


def race_as_of(race: config.Race, as_of: date) -> date:
    """The date an average is computed for: the midterm generic ballot stops at Election Day, so its final
    average stays the one voters went in with instead of drifting as the last polls age."""
    return min(as_of, config.MIDTERM_DAY_2026) if race.id == MIDTERM_RACE else as_of


def midterm_context(averages: dict[str, average.RaceAverage], as_of: date) -> dict | None:
    """The generic-ballot block shown on the home and approval pages from a week before the midterms to a month after."""
    days = (config.MIDTERM_DAY_2026 - as_of).days
    ra = averages.get(MIDTERM_RACE)
    if not ra or not ra.values or not -30 <= days <= 7:
        return None
    race = config.RACE_BY_ID[MIDTERM_RACE]
    return dict(days=days, ra=ra, race=race, path=f"/{race.slug}/", colors=race_colors(race))


def home_head(as_of: date, has_results: bool) -> dict:
    """Title, H1, lead and description of the home page: the midterms in election week, the
    polls-vs-results question once results are in, 2028 otherwise."""
    days = (config.MIDTERM_DAY_2026 - as_of).days
    if -30 <= days <= 7 and has_results:
        return dict(title="Did the Polls Get the 2026 Midterms Right?", h1="Did the polls get the 2026 midterms right?",
                    sub="Every final-weeks 2026 poll scored against the House result, the 2028 averages and the pollster scorecard.",
                    description="How close the 2026 midterm polls came to the result, pollster by pollster, plus open poll "
                                "averages and odds for the 2028 presidential election.")
    if -30 <= days <= 7:
        return dict(title="2026 Midterm Polls vs. Results, 2028 Odds", h1="2026 midterms: the final polls, then the results",
                    sub="The final generic ballot average, where to follow official results, and the 2028 averages. Ask a question or pick one below.",
                    description="The final 2026 midterm generic ballot average, poll closing times and official results "
                                "sources by state, and open poll averages and odds for 2028.")
    return dict(title="2028 Election Polls, Pollster Ratings, Odds", h1="How is 2028 looking?",
                sub="Polling averages, pollster accuracy and prediction-market odds for the next presidential election. Ask a question or pick one below.",
                description=config.SITE["description"])


def race_charts(ra: average.RaceAverage, race: config.Race) -> dict[str, str]:
    colors = race_colors(race)
    wide = ra.polls if ra.polls is not None else pd.DataFrame()
    points = {c: [(r["end_date"], float(r[c])) for _, r in wide.iterrows() if pd.notna(r[c])] for c in race.candidates} if not wide.empty else {}
    if race.kind == "primary":
        top = sorted(ra.values, key=ra.values.get, reverse=True)[:5]
        pc = primary_colors(race, top)
        line = charts.line_chart({c: ra.trend.get(c, []) for c in top}, {c: points.get(c, []) for c in top}, pc,
                                 title=f"{race.title}: polling average over time", chart_id="trend",
                                 short={c: short_name(c) for c in top})
        bars = charts.bar_chart({c: v for c, v in ra.values.items() if c != "Other/Undecided"}, pc,
                                title=f"{race.title}: current average", chart_id="bars")
        return {"line": line, "bars": bars}
    line = charts.line_chart({c: ra.trend.get(c, []) for c in race.candidates}, points, colors,
                             title=f"{race.title}: polling average over time", chart_id="trend",
                             short={c: short_name(c) for c in race.candidates})
    return {"line": line, "bars": ""}


def editor_ld() -> dict | None:
    """The named editor as a Person, once config.SITE["editor"] has a name."""
    e = config.SITE.get("editor") or {}
    if not e.get("name"):
        return None
    person = {"@type": "Person", "@id": f"{config.SITE['url']}/about/#editor", "name": e["name"], "jobTitle": e.get("role", ""),
              "url": f"{config.SITE['url']}/about/"}
    if e.get("same_as"):
        person["sameAs"] = e["same_as"]
    return person


def write_icons(dist: Path) -> None:
    """favicon.ico (48 px), a 180 px apple-touch-icon, 192/512 px app icons and a web manifest, from the avatar."""
    from PIL import Image
    src = Image.open(config.ROOT / "assets" / "social" / "x-avatar.png").convert("RGBA")
    src.resize((48, 48), Image.LANCZOS).save(dist / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)])
    img = dist / "static" / "img"
    src.convert("RGB").resize((180, 180), Image.LANCZOS).save(img / "apple-touch-icon.png")
    for n in (192, 512):
        src.resize((n, n), Image.LANCZOS).save(img / f"icon-{n}.png")
    manifest = {"name": config.SITE["name"], "short_name": config.SITE["name"], "start_url": "/", "display": "browser",
                "background_color": "#fbfbf9", "theme_color": "#0e0e0f",
                "icons": [{"src": f"/static/img/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png"} for n in (192, 512)]}
    (dist / "site.webmanifest").write_text(json.dumps(manifest, indent=1))


def site_ld() -> dict:
    """WebSite + Organization structured data, emitted on every page."""
    s = config.SITE
    org = {"@type": "Organization", "@id": f"{s['url']}/#org", "name": s["name"], "alternateName": s["alternate_name"],
           "url": s["url"], "logo": f"{s['url']}/static/img/logo.png", "foundingDate": s["founding_date"],
           "publishingPrinciples": f"{s['url']}/methodology/", "correctionsPolicy": f"{s['url']}/corrections/"}
    if editor_ld():
        org["founder"] = editor_ld()
    same_as = [f"https://x.com/{s['twitter'].lstrip('@')}"] if s.get("twitter") else []
    if s.get("github_repo"):
        same_as.append(f"https://github.com/{s['github_repo']}")
    if same_as:
        org["sameAs"] = same_as
    website = {"@type": "WebSite", "@id": f"{s['url']}/#website", "name": s["name"], "url": s["url"],
               "description": s["description"], "inLanguage": s["language"], "publisher": {"@id": org["@id"]}}
    return {"@context": "https://schema.org", "@graph": [website, org]}


def breadcrumb_ld(trail: list[tuple[str, str]]) -> dict:
    """trail: (name, path) for each level below Home, ending with the page itself."""
    base = config.SITE["url"]
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": f"{base}{path}"}
        for i, (name, path) in enumerate([("Home", "/"), *trail], start=1)
    ]}


def dataset_ld(race: config.Race, path: str, as_of: date, start: date | None = None) -> dict:
    base = config.SITE["url"]
    return {
        "@context": "https://schema.org", "@type": "Dataset", "name": f"{race.title} – polling average",
        "description": race.description, "url": f"{base}{path}", "dateModified": as_of.isoformat(),
        "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base},
        "maintainer": {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base},
        "spatialCoverage": {"@type": "Country", "name": "United States"},
        **({"temporalCoverage": f"{start.isoformat()}/{as_of.isoformat()}"} if start else {}),
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{base}/api/{race.id}.json"},
            {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/data/polls.csv"},
        ],
    }


def poll_list(polls: pd.DataFrame) -> list[dict]:
    """One summary per poll, newest first, credited to the firm that ran it (see pollsters.resolve)."""
    if polls.empty:
        return []
    out = []
    for pid, g in polls.groupby("poll_id"):
        race = config.RACE_BY_ID.get(g["race_id"].iat[0])
        if not race:
            continue
        r = g.iloc[0]
        vals = dict(zip(g["candidate"], g["pct"]))
        ordered = [c for c in race.candidates if c in vals]
        if race.kind == "primary":
            ordered = sorted((c for c in ordered if c != "Other/Undecided"), key=lambda c: -vals[c])[:3]
        headline = "  ·  ".join(f"{short_name(c)} {vals[c]:g}%" for c in ordered)
        a, b = (race.candidates + ["", ""])[:2]
        margin_label = signed(vals[a] - vals[b], short_name(a), short_name(b)) if race.kind != "primary" and a in vals and b in vals else ""
        sponsor = r["sponsor"] if isinstance(r["sponsor"], str) else ""
        firm, tag = pollsters.resolve(r["pollster"], sponsor) or (None, "")
        out.append(dict(poll_id=pid, race=race, pollster=r["pollster"], sponsor=sponsor, firm=firm, tag=tag,
                        partners=pollsters.partners(r["pollster"], sponsor, firm) if firm else "",
                        end_date=r["end_date"], dates=fmt_dates(r["start_date"], r["end_date"]),
                        sample=fmt_sample(r["sample_size"], r["population"]), headline=headline, margin_label=margin_label,
                        source_url=r["source_url"] if isinstance(r["source_url"], str) else ""))
    out.sort(key=lambda d: d["end_date"], reverse=True)
    return out


def markets_context(markets: pd.DataFrame, averages: dict[str, average.RaceAverage]) -> list[dict]:
    """Polymarket prices from the API only: no hand-entered press snapshots, no frozen contracts, one spelling per name."""
    out = []
    if markets.empty:
        return out
    markets = markets[(markets["platform"] == "polymarket") & (markets["source_type"] == "api")].copy()
    markets["snapshot_date"] = pd.to_datetime(markets["snapshot_date"]).dt.date
    markets["outcome"] = markets["outcome"].map(fetch_markets.canonical_outcome)
    markets = markets.drop_duplicates(["snapshot_date", "market_id", "outcome"], keep="last")
    for mk in config.MARKETS:
        sub = markets[markets["market_id"] == mk["id"]]
        if sub.empty:
            out.append(dict(market=mk, rows=[], chart="", latest=None, hidden=[], note="No snapshot yet. The pipeline records one on each run."))
            continue
        latest = sub["snapshot_date"].max()
        hidden = check_data.stale_prices(sub)
        snap = sub[(sub["snapshot_date"] == latest) & ~sub["outcome"].isin(hidden)].sort_values("price", ascending=False)
        rows = [dict(outcome=o, polymarket=float(p)) for o, p in zip(snap["outcome"], snap["price"])]
        chart = ""
        cmp_race = mk.get("compare_race")
        if cmp_race and cmp_race in averages and averages[cmp_race].values:
            av = averages[cmp_race].values
            groups = {}
            for r in rows[:8]:
                g = {"Polymarket": r["polymarket"]}
                if r["outcome"] in av:
                    g["Poll average"] = av[r["outcome"]]
                groups[r["outcome"]] = g
            chart = charts.grouped_bars(groups, {"Poll average": "#111827", "Polymarket": "#2563eb"},
                                        title=f"{mk['title']}: polls vs. prediction markets", chart_id=f"cmp-{mk['id']}")
        out.append(dict(market=mk, rows=rows, chart=chart, latest=latest, hidden=hidden, note=""))
    return out


# ------------------------------------------------------------------ states
def build_states(render, dist: Path, states: dict[str, history.StateHistory],
                 nation: dict[int, history.NationYear], as_of: date) -> list[dict]:
    """Render /states/, one page per state, their share cards and the results CSV; return finder entries."""
    year, base = max(nation), config.SITE["url"]
    nat, prev_year = nation[year], year - 4
    revised = min(config.PAGE_REVISED["results"], as_of)
    colors = {p: config.PARTY_COLORS[p] for p in ("DEM", "REP")}
    nat_series = [(y, n.margin) for y, n in sorted(nation.items())]
    hub = [("Results by state", "/states/")]
    creators = [{"@type": "Organization", "name": "MIT Election Data and Science Lab", "url": "https://electionlab.mit.edu/"},
                {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base}]
    csv_ld = {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/data/president-by-state.csv"}
    (dist / "og" / "states").mkdir(parents=True)
    ordered = list(states.values())
    index, csv_rows = [], []

    for i, st in enumerate(ordered):
        answer = history.answer_sentence(st, nation)
        rows = [dict(year=y.year, dem=y.dem, rep=y.rep, dem_pct=y.dem_pct, rep_pct=y.rep_pct, other_pct=y.other_pct,
                     other=y.other, other_votes=y.other_votes, total=y.total, winner=y.winner, margin_label=y.margin_label,
                     lean=history.fmt_lean(y.margin - nation[y.year].margin), ev=y.ev, ev_dem=y.ev_dem, ev_rep=y.ev_rep,
                     split_note=y.split_note, year_path=year_path(y.year, year)) for y in reversed(st.years)]
        chart = charts.margin_columns([(y.year, y.margin) for y in st.years], nat_series, colors,
                                      title=f"{st.name} presidential margin by election, 1976–{year}")
        ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"{st.name} presidential election results, 1976–{year}",
              "description": answer, "url": f"{base}{st.path}", "license": "https://creativecommons.org/publicdomain/zero/1.0/",
              "isAccessibleForFree": True, "temporalCoverage": f"1976/{year}",
              "spatialCoverage": {"@type": "Place", "name": f"{st.name}, United States"},
              "creator": creators, "distribution": [csv_ld]}
        (dist / "og" / "states" / f"{st.slug}.png").write_bytes(og_cards.state_image(st, nation, colors))
        render("state.html", st.path, title=f"{st.name} Presidential Election Results, 1976–{year}", description=answer,
               answer=answer, st=st, rows=rows, chart=chart, colors=colors, picked=st.picked_winner(nation),
               lean=history.fmt_lean(st.lean(nation)), nation_label=history.fmt_margin(nat.margin, nat.dem, nat.rep),
               prev=ordered[i - 1] if i else None, next=ordered[i + 1] if i + 1 < len(ordered) else None,
               crumb=st.name, trail=hub, og_image=f"/og/states/{st.slug}.png", ld_dataset=ld, lastmod=revised)
        y = st.latest
        index.append(dict(t=f"{st.name} election results", u=st.path, k="State", s=f"{year}: {y.margin_label} · {y.ev} electoral votes",
                          q=f"{st.name} {st.po} state results how did vote voted swing history electoral votes {year}"))
        csv_rows += [dict(year=y.year, state=st.name, state_po=st.po, electoral_votes=y.ev, dem_candidate=y.dem, dem_votes=y.dem_votes,
                          rep_candidate=y.rep, rep_votes=y.rep_votes, total_votes=y.total, dem_pct=round(y.dem_pct, 2),
                          rep_pct=round(y.rep_pct, 2), margin_r=round(y.margin, 2), ev_dem=y.ev_dem, ev_rep=y.ev_rep,
                          note=y.split_note) for y in st.years]

    # one results-by-state page per election: /states/ for the latest, /states/<year>/ for earlier ones
    years = [dict(year=yr, path=year_path(yr, year)) for yr in sorted(nation)]
    for yr in sorted(nation):
        n, path, prev = nation[yr], year_path(yr, year), (yr - 4 if yr - 4 in nation else None)
        rows = []
        for st in ordered:
            y, p = st.by_year(yr), st.by_year(prev) if prev else None
            rows.append(dict(name=st.name, path=st.path, cls=usmap.shade(y.margin), ev=y.ev, dem_pct=y.dem_pct, rep_pct=y.rep_pct,
                             other_pct=y.other_pct, margin=y.margin, margin_label=y.margin_label,
                             prev=p.margin if p else None, prev_label=p.margin_label if p else "",
                             shift=y.margin - p.margin if p else None, shift_label=history.fmt_lean(y.margin - p.margin) if p else ""))
        answer = history.national_sentence(states, nation, yr)
        ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"{yr} U.S. presidential election results by state",
              "description": answer, "url": f"{base}{path}", "license": "https://creativecommons.org/publicdomain/zero/1.0/",
              "isAccessibleForFree": True, "temporalCoverage": str(yr), "creator": creators, "distribution": [csv_ld]}
        og = "/og/states.png" if yr == year else f"/og/states/{yr}.png"
        (dist / og.lstrip("/")).write_bytes(og_cards.states_image(n, colors))
        latest = yr == year
        render("states.html", path, description=answer, answer=answer, year=yr, latest_year=year, years=years,
               prev_year=prev, nation=n, rows=rows, show_other=n.other_pct >= history.NOTABLE_OTHER,
               title=f"{yr} Election Results by State: Map, Margins and Electoral Votes" if latest
               else f"{yr} Presidential Election Results by State: Map and Electoral Votes",
               usmap=usmap.map_context(states, yr), evbar=usmap.ev_bar(n),
               crumb="Results by state" if latest else str(yr), trail=[] if latest else hub,
               split_notes=[st.by_year(yr).split_note for st in ordered if st.by_year(yr).split_note],
               og_image=og, ld_dataset=ld, lastmod=revised)
        index.append(dict(t=f"{yr} election results by state", u=path, k="Map",
                          s=f"{history.short(n.rep)} {n.ev_rep}, {history.short(n.dem)} {n.ev_dem} electoral votes",
                          q=f"{yr} map results by state electoral college who won {n.dem} {n.rep} swing states red blue"))
    pd.DataFrame(csv_rows).to_csv(dist / "data" / "president-by-state.csv", index=False)
    return index


def build_map_builder(render, dist: Path, states: dict[str, history.StateHistory],
                      nation: dict[int, history.NationYear], as_of: date) -> list[dict]:
    """Render /2028/map/, the electoral map builder that starts from the latest result; return its finder entry."""
    year, base = max(nation), config.SITE["url"]
    n = nation[year]
    ctx = usmap.builder_context(states, year)
    winner, loser = ("R", "D") if n.ev_rep > n.ev_dem else ("D", "R")
    party = {"D": "Democrats", "R": "Republicans"}
    answer = (f"{n.rep if winner == 'R' else n.dem} won {year} with {max(n.ev_rep, n.ev_dem)} electoral votes to "
              f"{min(n.ev_rep, n.ev_dem)}; 2028 uses the same electoral-vote allocation.")
    tp = usmap.tipping_point(ctx["units"], loser)
    if tp:
        u, swing = tp
        answer += (f" Starting from that map, a uniform swing of more than {swing:.1f} points toward {party[loser]} "
                   f"would flip {u['n']} and give them 270.")
    answer += " Tap states to flip them, swing every state at once, and share your forecast."
    colors = {p: config.PARTY_COLORS[p] for p in ("DEM", "REP")}
    (dist / "og" / "map.png").write_bytes(og_cards.map_image(n, colors))
    closest = sorted((u for u in ctx["units"] if u["m"] is not None), key=lambda u: abs(u["m"]))[:10]
    ld = {"@context": "https://schema.org", "@type": "WebApplication", "name": "2028 electoral map builder",
          "url": f"{base}/2028/map/", "description": answer, "applicationCategory": "ReferenceApplication",
          "operatingSystem": "Any", "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
          "creator": {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base}}
    render("map_builder.html", "/2028/map/", title="2028 Electoral Map: Make Your Own Forecast", description=answer,
           answer=answer, year=year, nation=n, usmap=ctx, closest=closest, tipping=tp,
           evbar=dict(ev_dem=n.ev_dem, ev_rep=n.ev_rep, dem_w=round(100 * n.ev_dem / 538, 2), rep_w=round(100 * n.ev_rep / 538, 2)),
           builder=dict(year=year, units=ctx["units"]), crumb="2028 electoral map", og_image="/og/map.png", ld_app=ld,
           lastmod=min(config.PAGE_REVISED["results"], as_of))
    return [dict(t="2028 electoral map builder", u="/2028/map/", k="Map", s="Make your own forecast: flip states, swing the map, share it",
                 q="2028 electoral map interactive make your own forecast prediction 270 to win swing states simulator scenario build")]


def clock(hhmm: str) -> str:
    """"19:00" -> "7 p.m.", "19:30" -> "7:30 p.m.", "00:00" -> "midnight"."""
    h, m = map(int, hhmm.split(":"))
    if h == 0 and m == 0:
        return "midnight"
    return f"{(h - 1) % 12 + 1}{f':{m:02d}' if m else ''} {'a.m.' if h < 12 else 'p.m.'}"


def midterm_status(as_of: date) -> str:
    days = (config.MIDTERM_DAY_2026 - as_of).days
    if days > 1:
        return f"in {days} days"
    if days == 1:
        return "tomorrow"
    if days == 0:
        return "Election Day is today"
    return "votes are being counted; results are unofficial until certified" if days >= -35 else "results certified"


def build_midterm_hub(render, averages: dict[str, average.RaceAverage], states: dict[str, history.StateHistory],
                      as_of: date, result: str = "") -> list[dict]:
    """Render /2026/: the final generic ballot average, poll closing times and each state's official results site."""
    ra = averages[MIDTERM_RACE]
    race = config.RACE_BY_ID[MIDTERM_RACE]
    src = json.loads((config.DATA_DIR / "elections" / "2026-states.json").read_text())
    by_po = {st.po: st.path for st in states.values()}
    rows = []
    for s in src["states"]:
        close = clock(s["close_et"]) + (f"–{clock(s['last_close_et'])}" if s["last_close_et"] else "")
        rows.append(dict(name=s["name"], path=by_po.get(s["po"], "/states/"), url=s["url"], authority=s["authority"],
                         close=close + (" (Nov 4)" if s["next_day"] else ""), note=s["note"]))
    first = min(src["states"], key=lambda s: s["close_et"] if not s["next_day"] else "99")
    earliest = [s for s in src["states"] if s["close_et"] == first["close_et"] and not s["next_day"]]
    where = ("parts of " if all(s["last_close_et"] for s in earliest) else "") + " and ".join(s["name"] for s in earliest)
    margin = signed(ra.margin, "Democrats", "Republicans") if ra.margin is not None else "even"
    answer = (f"The 2026 midterm elections were held on Tuesday, November 3, 2026. The final ElectionsUSA generic ballot "
              f"average had {margin} ({ra.n_polls} polls). Official results come from each state's election office, "
              f"linked below with poll closing times.") if as_of > config.MIDTERM_DAY_2026 else (
              f"The 2026 midterm elections are on Tuesday, November 3, 2026; the first polls close at {clock(first['close_et'])} ET. "
              f"The final ElectionsUSA generic ballot average has {margin} ({ra.n_polls} polls). Official results come "
              f"from each state's election office, linked below with every state's poll closing time.")
    faq = [
        ("When do polls close on November 3, 2026?",
         f"The first polls close at {clock(first['close_et'])} Eastern Time in {where}; most of the East closes "
         "between 7 and 8 p.m. ET, and the last polls, in Alaska and Hawaii, close at midnight to 1 a.m. ET on November 4. "
         "The table lists every state."),
        ("Who won the House and the Senate?",
         "ElectionsUSA does not call races. Each state's election office publishes the unofficial count on election night and "
         "certifies the result in the following weeks; news organisations project winners from those counts. Use the "
         "official results links in the table for each state."),
        ("What did the final polls say?",
         f"The final generic ballot average had {margin}: {', '.join(f'{c} {ra.values[c]:.1f}%' for c in race.candidates if c in ra.values)}, "
         f"from {ra.n_polls} national polls. The generic ballot measures the national House vote, not seats."),
        ("How will you check the polls against the results?",
         "We compare the final average with the national House popular vote and score every poll from the last three weeks "
         "of the campaign on the 2026 pollster scorecard: first with the unofficial count, labelled preliminary, then with "
         "certified results."),
    ]
    hub = dict(ra=ra, race=race, path=f"/{race.slug}/", colors=race_colors(race), states=rows, status=midterm_status(as_of),
               sources=src["closing_sources"], checked="November 3, 2026", result=result)
    render("midterm_hub.html", "/2026/", hub=hub, answer=answer, faq=faq, ld_faq=faq_ld(faq),
           title="2026 Midterm Elections: Final Polls, Poll Closing Times, Results",
           description=answer, crumb="2026 midterms", og_image=f"/og/{MIDTERM_RACE}.png",
           lastmod=min(as_of, config.MIDTERM_DAY_2026 + timedelta(days=1)))
    return [dict(t="2026 midterms: House and Senate results, poll closing times", u="/2026/", k="Midterms",
                 s=f"Final generic ballot {margin} · when polls close · official results by state",
                 q="2026 midterm midterms election elections house senate governor governors congress control results result "
                   "won win winner winners called call election night tonight today poll closing times close vote count")]


HUB_2028 = ("2028 election", "/2028/")
HUB_PRESIDENT = ("2028 president", "/2028/president/")


def race_trail(race: config.Race) -> list[tuple[str, str]]:
    """Breadcrumb levels above a race page: /2028/ and, for matchups, /2028/president/."""
    if race.slug.startswith("2028/president/"):
        return [HUB_2028, HUB_PRESIDENT]
    return [HUB_2028] if race.slug.startswith("2028/") else []


def build_2028_hubs(render, summaries: list[dict], race_lastmod: dict[str, date | None], as_of: date) -> list[dict]:
    """Render /2028/ (every 2028 average plus the map, calendar and markets) and /2028/president/ (the matchups)."""
    matchups = [s for s in summaries if s["race"].slug.startswith("2028/president/")]
    all_2028 = [s for s in summaries if s["race"].slug.startswith("2028/")]

    def lead(s) -> str:
        r, a = s["race"], s["avg"]
        if not a.values:
            return f"{r.short_title}: no polls yet"
        if r.kind == "primary":
            top = og_cards.ranked(a)[0]
            return f"{top} leads the {r.short_title} at {a.values[top]:.1f}%"
        return f"{r.short_title}: {signed(a.margin, short_name(r.candidates[0]), short_name(r.candidates[1]))}"

    def newest(group) -> date | None:
        return max((race_lastmod[s["race"].id] for s in group if race_lastmod.get(s["race"].id)), default=None)

    answer = (f"ElectionsUSA tracks {len(matchups)} hypothetical 2028 general-election matchups. "
              + "; ".join(lead(s) for s in matchups) + ". Early matchup polls measure name recognition as much as preference.")
    render("hub.html", "/2028/president/", kicker="2028 presidential election", heading="2028 Presidential Election Polls",
           answer=answer, cards=matchups, links=[dict(title="2028 electoral map", path="/2028/map/", value="Make your own forecast"),
                                                 dict(title="Prediction markets", path="/markets/", value="Odds vs. the polls")],
           links_heading="More on 2028", title="2028 Presidential Election Polls: Every Matchup", description=answer,
           crumb="2028 president", trail=[HUB_2028], lastmod=newest(matchups))
    answer = ("The 2028 presidential election is on November 7, 2028. "
              + "; ".join(lead(s) for s in all_2028 if s["race"].kind == "primary")
              + ". Every poll average, the primary calendar, the electoral map and market odds for 2028, in one place.")
    render("hub.html", "/2028/", kicker="2028 election", heading="2028 Election: Polls, Primaries and Map", answer=answer,
           cards=all_2028, links_heading="Plan the race",
           links=[dict(title="2028 presidential matchups", path="/2028/president/", value=f"{len(matchups)} head-to-head averages"),
                  dict(title="2028 electoral map", path="/2028/map/", value="Make your own forecast"),
                  dict(title="2028 primary calendar", path="/2028/calendar/", value="South Carolina votes first, Jan 22"),
                  dict(title="Prediction markets", path="/markets/", value="Odds vs. the polls"),
                  dict(title="Countdown", path="/countdown/", value=f"{(config.ELECTION_DAY_2028 - as_of).days} days to go")],
           title="2028 Election Polls, Primaries, Map and Calendar", description=answer, crumb="2028 election", lastmod=newest(all_2028))
    return [dict(t="2028 presidential election polls", u="/2028/president/", k="Hub", s="Every 2028 head-to-head matchup average",
                 q="2028 president presidential election general matchup head to head polls hub all"),
            dict(t="2028 election hub", u="/2028/", k="Hub", s="Every 2028 average, the primary calendar, map and odds",
                 q="2028 election hub overview primaries president all averages")]


def build_machine_files(dist: Path, summaries: list[dict], race_lastmod: dict[str, date | None],
                        answers: dict[str, str], entries: list[dict], as_of: date) -> None:
    """llms.txt (what the site is, today's numbers, where the data is, how to cite it) and an Atom feed."""
    base, name = config.SITE["url"], config.SITE["name"]
    lines = [f"# {name} ({config.SITE['alternate_name']})", "",
             f"> {config.SITE['description']}", "",
             f"Independent, non-partisan U.S. poll averages with an open method. Built {as_of.isoformat()}; data refreshes every six hours.", "",
             "## Current averages"]
    for s in summaries:
        r = s["race"]
        when = race_lastmod.get(r.id)
        lines.append(f"- [{r.title}]({base}/{r.slug}/): {answers.get(r.id) or 'no polls yet'}"
                     + (f" (latest poll {when.isoformat()})" if when else ""))
    lines += ["", "## Key pages",
              f"- [2026 midterms: final polls, poll closing times, official results]({base}/2026/)",
              f"- [2028 election hub]({base}/2028/)",
              f"- [Pollster scorecard: accuracy and bias of 60+ pollsters]({base}/pollsters/)",
              f"- [Methodology]({base}/methodology/)",
              f"- [Corrections log]({base}/corrections/)", "",
              "## Data and API (static files, no key, no rate limit)",
              f"- [Every poll, one row per candidate, with a source link per row (CSV)]({base}/data/polls.csv)",
              f"- [Pollster scorecard (CSV)]({base}/data/pollster-scorecard.csv)",
              f"- [Presidential results by state, 1976 onward (CSV)]({base}/data/president-by-state.csv)",
              f"- [Polymarket snapshots (CSV)]({base}/data/markets.csv)"]
    lines += [f"- [{s['race'].title} average, trend and polls (JSON)]({base}/api/{s['race'].id}.json)" for s in summaries]
    lines += ["", "## License and attribution",
              "- Our compilation, averages, scorecard and charts: CC BY 4.0. Fields compiled from Wikipedia: CC BY-SA 4.0. "
              "Prediction-market prices: subject to the platform's terms.",
              f"- Cite as: \"{name} polling average, {base}/<page>/ (accessed <date>)\". Please link the page you used.",
              "- We do not forecast or call races; poll numbers are the pollsters' own and are credited on every row.", ""]
    (dist / "llms.txt").write_text("\n".join(lines), encoding="utf-8")

    from xml.sax.saxutils import escape
    updated = max((e["updated"] for e in entries), default=as_of)
    feed = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <title>{escape(name)}: poll averages and analysis</title>", f'  <link href="{base}/"/>',
            f'  <link rel="self" href="{base}/feed.xml"/>', f"  <id>{base}/</id>", f"  <updated>{updated.isoformat()}T00:00:00Z</updated>",
            f"  <author><name>{escape(config.SITE['editor'].get('name') or config.SITE['author'])}</name></author>"]
    for e in sorted(entries, key=lambda e: e["updated"], reverse=True):
        feed += ["  <entry>", f"    <title>{escape(e['title'])}</title>", f'    <link href="{base}{e["path"]}"/>',
                 f"    <id>{base}{e['path']}</id>", f"    <updated>{e['updated'].isoformat()}T00:00:00Z</updated>",
                 f"    <summary>{escape(e['summary'])}</summary>", "  </entry>"]
    feed.append("</feed>")
    (dist / "feed.xml").write_text("\n".join(feed) + "\n", encoding="utf-8")


def article_ld(a: dict, image: str) -> dict:
    base = config.SITE["url"]
    org = {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base,
           "logo": {"@type": "ImageObject", "url": f"{base}/static/img/logo.png"}}
    return {"@context": "https://schema.org", "@type": "Article", "headline": a["headline"], "description": a["dek"],
            "datePublished": a["published"].isoformat(), "dateModified": a["modified"].isoformat(),
            "author": editor_ld() or org, "publisher": org, "mainEntityOfPage": f"{base}{a['path']}",
            "image": {"@type": "ImageObject", "url": f"{base}{image}", "width": 1200, "height": 630}, "inLanguage": "en"}


def build_accuracy_and_analysis(render, dist: Path, polls: pd.DataFrame,
                                averages: dict[str, average.RaceAverage], pollster_path, as_of: date) -> tuple[list[dict], list[dict]]:
    """Render /2026/pollster-accuracy/ and /analysis/; return (finder entries, feed entries)."""
    result = accuracy.load_result()
    if result and result.as_of > as_of:
        result = None  # a build for an earlier date must not know the result
    final = averages[MIDTERM_RACE]
    polls_final = accuracy.final_polls(polls)
    rows = accuracy.score(polls_final, result)
    for r in rows:
        r["path"] = pollster_path(r["pollster"])
    answer = accuracy.answer(rows, result, final.margin)
    window_start = config.MIDTERM_DAY_2026 - timedelta(days=accuracy.WINDOW_DAYS)
    csv = pd.DataFrame([dict(poll_id=p["poll_id"], pollster=p["pollster"], listed_as=p["listed"], sponsor=p["sponsor"],
                             end_date=p["end_date"], population=p["population"], sample_size=p["sample_size"], dem=p["dem"],
                             rep=p["rep"], margin=p["margin"],
                             result_margin=result.margin if result else None,
                             error=round(abs(p["margin"] - result.margin), 1) if result else None,
                             bias=round(p["margin"] - result.margin, 1) if result else None,
                             result_status=result.status if result else "pending", source_url=p["source_url"]) for p in polls_final])
    csv.to_csv(dist / "data" / "2026-generic-ballot-accuracy.csv", index=False)
    base = config.SITE["url"]
    acc_lastmod = min(result.as_of if result else config.MIDTERM_DAY_2026, as_of)
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "2026 generic ballot pollster accuracy",
          "description": answer, "url": f"{base}/2026/pollster-accuracy/", "dateModified": acc_lastmod.isoformat(),
          "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True, "temporalCoverage": f"{window_start.isoformat()}/2026-11-03",
          "spatialCoverage": {"@type": "Country", "name": "United States"},
          "creator": {"@type": "Organization", "@id": f"{base}/#org", "name": config.SITE["name"], "url": base},
          "variableMeasured": ["poll margin", "error against the House popular vote", "partisan bias"],
          "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/data/2026-generic-ballot-accuracy.csv"}]}
    render("pollster_accuracy.html", "/2026/pollster-accuracy/", result=result, rows=rows, answer=answer, final=final,
           fmt=accuracy.fmt_margin, bias=accuracy.bias_label, window_start=window_start, ld_dataset=ld,
           title="Most Accurate 2026 Pollsters: Generic Ballot vs. Result" + (" (Preliminary)" if result and result.preliminary else ""),
           description=answer, crumb="2026 pollster accuracy", trail=[("2026 midterms", "/2026/")],
           og_image=f"/og/{MIDTERM_RACE}.png", lastmod=acc_lastmod)

    # --- analysis pieces, all computed from the data
    articles = []
    fmt = accuracy.fmt_margin
    trend = final.trend.get("Democrats", [])
    rep_trend = dict(final.trend.get("Republicans", []))
    month = next(((d, v - rep_trend[d]) for d, v in reversed(trend) if (final.as_of - d).days >= 30 and d in rep_trend), None)
    margins = [p["margin"] for p in polls_final]
    by_pop: dict[str, list[float]] = {}
    for p in polls_final:
        by_pop.setdefault(p["population"] or "unknown", []).append(p["margin"])
    pop_names = {"LV": "likely-voter", "RV": "registered-voter", "A": "all-adult", "unknown": "unstated-population"}
    if final.values and margins:
        slug = "final-generic-ballot-2026"
        published = config.ANALYSIS_PUBLISHED[slug]
        modified = max(published, min(pd.Timestamp(final.latest_end_date).date(), as_of))
        a = dict(path=f"/analysis/{slug}/", published=min(published, as_of), modified=min(modified, as_of),
                 headline=f"Final generic ballot {fmt(final.margin)}: what the polls said going into Election Day",
                 dek=(f"The final ElectionsUSA average of {final.n_polls} national polls had Democrats at {final.values['Democrats']:.1f}% "
                      f"and Republicans at {final.values['Republicans']:.1f}%, a {fmt(final.margin)} margin, going into the "
                      "November 3, 2026 midterms."))
        body = [dict(h="The final number", p=(
                    f"Going into Election Day the ElectionsUSA generic ballot average stood at {fmt(final.margin)}: Democrats "
                    f"{final.values['Democrats']:.1f}%, Republicans {final.values['Republicans']:.1f}%. It weights {final.n_polls} "
                    f"of the {final.n_polls_total} national polls on record by recency, sample size, pollster record and how often "
                    f"each firm publishes; the last poll in it ended {pd.Timestamp(final.latest_end_date).strftime('%B %-d')}. "
                    "The generic ballot measures the national House vote, not seats: district lines and uncontested races mean "
                    "a national lead does not translate one-for-one into the House majority."))]
        if month:
            d, m = month
            move = final.margin - m
            body.append(dict(h="How it moved", p=(
                f"On {d.strftime('%B %-d')} the average was {fmt(m)}, so the final month moved it "
                + (f"{abs(move):.1f} points toward {'Democrats' if move > 0 else 'Republicans'}." if abs(move) >= 0.05 else "not at all.")
                + ' The <a href="/2026/generic-ballot/">trend chart</a> shows the average as it stood on each date, without hindsight.')))
        body.append(dict(h="The final three weeks, pollster by pollster", p=(
            f"{len(polls_final)} polls from {len(rows)} pollsters ended between {window_start.strftime('%B %-d')} and Election Day. "
            f"Their margins ranged from {fmt(min(margins))} to {fmt(max(margins))}. The pollsters with the most polls in that window:"),
            table=dict(head=["Pollster", "Polls", "Average margin", "Last poll"],
                       rows=[[r["pollster"], r["n"], fmt(r["margin"]), r["last_end"].strftime("%b %-d")] for r in rows[:12]])))
        if len(by_pop) > 1:
            body.append(dict(h="Likely voters and registered voters", p=(
                "Where a pollster published several populations we use one, likely voters first. Across the final three weeks: "
                + "; ".join(f"{len(v)} {pop_names.get(k, k)} poll{'s' if len(v) != 1 else ''} averaged {fmt(sum(v) / len(v))}"
                            for k, v in sorted(by_pop.items(), key=lambda kv: -len(kv[1]))) + ".")))
        body.append(dict(h="What comes next", p=(
            'Once the national House popular vote has been counted we score every one of these polls against it on '
            '<a href="/2026/pollster-accuracy/">the 2026 pollster accuracy page</a>, first with the unofficial count, '
            'labelled preliminary, then with certified results. Poll closing times and each state\'s official results are on the '
            '<a href="/2026/">2026 midterms page</a>.')))
        a["body"] = body
        articles.append(a)
    if result and rows:
        slug = "polls-vs-results-2026-house-popular-vote"
        published = min(config.ANALYSIS_PUBLISHED.get(slug, result.as_of), as_of)
        label = "preliminary " if result.preliminary else ""
        errs = [p["margin"] - result.margin for p in polls_final]
        avg_bias = sum(errs) / len(errs)
        a = dict(path=f"/analysis/{slug}/", published=published, modified=min(result.as_of, as_of),
                 headline=f"Polls vs. results: the {label}2026 House popular vote",
                 dek=(f"The {label}House popular vote is {fmt(result.margin)}; the final ElectionsUSA average was {fmt(final.margin)}, "
                      f"a miss of {abs(final.margin - result.margin):.1f} points."))
        a["body"] = [
            dict(h="The result so far", p=(
                f"Democrats {result.dem_pct:.1f}%, Republicans {result.rep_pct:.1f}% ({fmt(result.margin)})"
                + (f", with about {result.counted_pct:.0f}% of the expected vote counted" if result.counted_pct is not None and result.preliminary else "")
                + f", as of {result.as_of.strftime('%B %-d, %Y')}, according to <a href=\"{result.source_url}\" rel=\"nofollow noopener\">{result.source}</a>."
                + (" These are unofficial figures; they will move as late ballots are counted and states certify." if result.preliminary else ""))),
            dict(h="How the polls did", p=(
                f"The final average missed by {abs(final.margin - result.margin):.1f} points. Across all {len(polls_final)} polls from the "
                f"final three weeks the average signed miss was {accuracy.bias_label(round(avg_bias, 1))} "
                "(D+ means the polls were more favourable to Democrats than the result). Closest pollsters first:"),
                table=dict(head=["Pollster", "Polls", "Average margin", "Error", "Bias"],
                           rows=[[r["pollster"], r["n"], fmt(r["margin"]), f"{r['error']:.1f}", accuracy.bias_label(r["bias"])] for r in rows[:12]])),
            dict(h="Full table", p='Every pollster and every poll, with the CSV, is on <a href="/2026/pollster-accuracy/">the 2026 pollster accuracy page</a>.'),
        ]
        articles.append(a)
    byline = (config.SITE["editor"].get("name") or config.SITE["author"])
    for a in articles:
        render("article.html", a["path"], article=a, byline=byline, ld_article=article_ld(a, f"/og/{MIDTERM_RACE}.png"),
               title=a["headline"], description=a["dek"], og_image=f"/og/{MIDTERM_RACE}.png", og_type="article",
               crumb=a["headline"], trail=[("Analysis", "/analysis/")], lastmod=a["modified"])
    articles.sort(key=lambda a: a["published"], reverse=True)
    if articles:
        render("analysis_index.html", "/analysis/", articles=articles, title="Analysis: What the Polls Say",
               description="Dated analysis of U.S. election polls from ElectionsUSA, built from open data.", crumb="Analysis",
               lastmod=max(a["modified"] for a in articles))
    finder = [dict(t="Which pollster was most accurate in 2026?", u="/2026/pollster-accuracy/", k="Scorecard", s=answer[:120],
                   q="2026 most accurate pollster pollsters accuracy midterm generic ballot error bias best worst preliminary result")]
    finder += [dict(t=a["headline"], u=a["path"], k="Analysis", s=a["dek"][:120], q="analysis article generic ballot 2026 midterm polls result") for a in articles]
    feed = [dict(title=a["headline"], path=a["path"], updated=a["modified"], summary=a["dek"]) for a in articles]
    return finder, feed


def year_path(yr: int, latest: int) -> str:
    return "/states/" if yr == latest else f"/states/{yr}/"


# --------------------------------------------------------------- pollsters
def pollster_ld(p: pollsters.Pollster, answer: str, lastmod: date, faq: list[tuple[str, str]]) -> list[dict]:
    """WebPage about the pollster's Organization, a Dataset of its scored record, and the FAQ."""
    base = config.SITE["url"]
    org = {"@id": f"{base}/#org", "@type": "Organization", "name": config.SITE["name"], "url": base}
    page = {"@context": "https://schema.org", "@type": "WebPage", "url": f"{base}{p.path}", "name": f"{p.name}: accuracy, bias and polls",
            "description": answer, "dateModified": lastmod.isoformat(), "about": {"@type": "Organization", "name": p.name},
            "publisher": org}
    out = [page]
    if p.rated:
        out.append({"@context": "https://schema.org", "@type": "Dataset", "name": f"{p.name} pollster accuracy record",
                    "description": answer, "url": f"{base}{p.path}", "dateModified": lastmod.isoformat(),
                    "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
                    "creator": org, "temporalCoverage": "2016/2022",
                    "variableMeasured": ["mean absolute error on the final margin", "mean signed error (partisan bias)", "share of polls with the winner ahead"],
                    "isBasedOn": "https://github.com/fivethirtyeight/data/tree/master/pollster-ratings",
                    "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{base}/data/pollster-scorecard.csv"}]})
    if faq:
        out.append(faq_ld(faq))
    return out


def pollster_faq(p: pollsters.Pollster, n_rated: int, field: float) -> list[tuple[str, str]]:
    r = p.rated
    if not r:
        return []
    better = "better" if r.mean_abs_error < field else "worse"
    lean = ("Its misses show no consistent partisan lean: the average signed error is under 0.3 points." if abs(r.mean_bias) < 0.3 else
            f"Its polls leaned {abs(r.mean_bias):.1f} points toward {'Democrats' if r.mean_bias > 0 else 'Republicans'} on average, "
            "measured against the final results.")
    return [
        (f"Is {p.name} accurate?",
         f"In the final three weeks of {r.cycles} races, {pollsters.possessive(p.name)} {r.n_polls} rated polls missed the final margin by "
         f"{r.mean_abs_error:.1f} points on average, {better} than the {field:.1f}-point average of all rated pollsters, and "
         f"{r.right_call_pct:.0f}% had the winner ahead. It ranks {pollsters.ordinal(p.rank)} of {n_rated} on the ElectionsUSA scorecard."),
        (f"Does {p.name} lean Democratic or Republican?", lean),
    ]


def build_pollsters(render, pages: dict[str, pollsters.Pollster], rated: list[scorecard.PollsterRow],
                    cycle_rows: list[dict], as_of: date, field: float) -> list[dict]:
    """Render one page per pollster (see pollsters.registry); return finder entries."""
    raw, _ = scorecard.load_538()
    by_rank = {p.rank: p for p in pages.values() if p.rank}
    index = []
    for p in pages.values():
        r = p.rated
        answer = pollsters.answer_sentence(p, len(rated))
        lastmod = max(min(p.polls[0]["end_date"], as_of) if p.polls else date.min, min(config.PAGE_REVISED["scorecard"], as_of))
        faq = pollster_faq(p, len(rated), field)
        render("pollster.html", p.path, p=p, answer=answer, description=answer, n_rated=len(rated), field_error=field,
               faq=faq, ld_page=pollster_ld(p, answer, lastmod, faq),
               record=pollsters.track_record(raw, r.rating_id) if r else None,
               cycle=[c for c in cycle_rows if c["pollster_path"] == p.path],
               prev=by_rank.get(p.rank - 1) if p.rank else None, next=by_rank.get(p.rank + 1) if p.rank else None,
               title=f"Is {p.name} Accurate? Pollster Rating, Bias and Polls" if r else f"{p.name} Polls: Every Recent Result",
               crumb=p.name, trail=[("Pollster scorecard", "/pollsters/")],
               lastmod=lastmod)
        index.append(dict(t=p.name, u=p.path, k="Pollster",
                          s=f"Avg error {r.mean_abs_error}, bias {r.bias_label}, {r.n_polls} rated polls" if r else f"{len(p.polls)} polls on record",
                          q=f"{p.name} pollster polls poll accuracy accurate rating rated grade bias biased reliable"))
    return index


# ------------------------------------------------------------------- build
def build(as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    polls, markets, ratings = load_data()
    env = Environment(loader=FileSystemLoader(str(config.TEMPLATE_DIR)), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["signed"] = signed
    env.filters["short"] = short_name
    env.filters["ordinal"] = pollsters.ordinal
    env.globals.update(site=config.SITE, nav=nav_items(as_of), nav_more=NAV_MORE, build_date=as_of.strftime("%B %-d, %Y"),
                       build_iso=as_of.isoformat(), year=as_of.year,
                       election_day=config.ELECTION_DAY_2028, midterm_day=config.MIDTERM_DAY_2026,
                       days_to_election=(config.ELECTION_DAY_2028 - as_of).days,
                       days_to_midterm=(config.MIDTERM_DAY_2026 - as_of).days,
                       races=config.RACES, ld_site=site_ld())

    dist = config.DIST_DIR
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    shutil.copytree(config.STATIC_DIR, dist / "static")
    shutil.copy(config.ROOT / "assets" / "social" / "x-avatar.png", dist / "static" / "img" / "logo.png")
    write_icons(dist)
    (dist / "api").mkdir()
    (dist / "data").mkdir()
    (dist / "og").mkdir()
    pages: list[tuple[str, date | None]] = []  # (path, sitemap lastmod); None = no meaningful date

    def render(template: str, out_path: str, lastmod: date | None = None, crumb: str | None = None,
               trail: list[tuple[str, str]] | None = None, **ctx) -> None:
        page = not out_path.endswith(".html")
        crumbs = None
        if page and out_path != "/":
            crumbs = breadcrumb_ld([*(trail or []), (crumb or ctx.get("title") or "", out_path)])
        html = env.get_template(template).render(path=out_path, ld_breadcrumb=crumbs, updated=lastmod, **ctx)
        target = dist / out_path.strip("/") / "index.html" if out_path != "/" else dist / "index.html"
        if not page:
            target = dist / out_path.strip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        if page and not ctx.get("noindex"):
            pages.append((out_path, lastmod))

    # pollster pages are known before the race pages render, so poll tables can link to them
    sc_rows = scorecard.historical_scorecard()
    all_polls = poll_list(polls)
    pollster_pages = pollsters.registry(all_polls, sc_rows)

    def pollster_path(pollster: str, sponsor: str = "") -> str | None:
        f = pollsters.firm(pollster, sponsor)
        page = pollster_pages.get(pollsters.key(f)) if f else None
        return page.path if page else None

    for q in all_polls:
        q["pollster_path"] = pollster_path(q["pollster"], q["sponsor"])

    # every average first, so any page can point at another (the midterm block, related averages)
    averages = {race.id: average.compute_race(polls, race, ratings, as_of=race_as_of(race, as_of)) for race in config.RACES}
    env.globals["midterm"] = midterm_context(averages, as_of)
    summaries = []
    answers: dict[str, str] = {}
    race_lastmod: dict[str, date | None] = {}
    for race in config.RACES:
        ra = averages[race.id]
        table = race_table(ra, race, ratings, pollster_path)
        ch = race_charts(ra, race)
        summaries.append(dict(race=race, avg=ra, colors=race_colors(race), path=f"/{race.slug}/"))
        shown = [c for c in race.candidates if any(r["vals"].get(c) is not None for r in table)
                 and (race.kind != "primary" or c != "Other/Undecided")]
        og_image = None
        if ra.values:
            colors = primary_colors(race, sorted(ra.values, key=ra.values.get, reverse=True)[:5]) if race.kind == "primary" else race_colors(race)
            (dist / "og" / f"{race.id}.png").write_bytes(og_cards.race_image(race, ra, colors, as_of))
            og_image = f"/og/{race.id}.png"
        # a page changes meaningfully when a new poll lands, not every time the build runs
        race_lastmod[race.id] = min(pd.Timestamp(ra.latest_end_date).date(), as_of) if ra.latest_end_date is not None else None
        answer = answer_sentence(race, ra, ra.as_of)
        answers[race.id] = answer
        faq = faq_items(race, ra, answer)
        thin = bool(ra.values) and ra.n_polls < THIN_POLLS
        render("race.html", f"/{race.slug}/", race=race, avg=ra, table=table, charts=ch, colors=race_colors(race),
               thin=thin, noindex=thin, max_rows=MAX_TABLE_ROWS,
               shown=shown, title=seo_title(race, ra, as_of), description=answer or race.description, answer=answer,
               faq=faq, ld_faq=faq_ld(faq) if faq else None, related=related_averages(race, averages),
               crumb=race.short_title, trail=race_trail(race), og_image=og_image, lastmod=race_lastmod[race.id],
               ld_dataset=dataset_ld(race, f"/{race.slug}/", race_lastmod[race.id] or as_of,
                                     ra.polls["end_date"].min() if ra.polls is not None and not ra.polls.empty else None))
        api = dict(race_id=race.id, title=race.title, as_of=as_of.isoformat(), method="https://electionsusa.org/methodology/",
                   average=ra.values, margin=ra.margin, n_polls_weighted=ra.n_polls, n_polls_total=ra.n_polls_total,
                   trend={c: [(d.isoformat(), v) for d, v in s] for c, s in ra.trend.items()},
                   polls=[{k: v for k, v in row.items() if k != "pollster_path"} for row in table])
        (dist / "api" / f"{race.id}.json").write_text(json.dumps(api, indent=1, default=str))

    cycle_rows = []
    res_path = config.DATA_DIR / "results" / "2026.csv"
    if res_path.exists():
        cycle_rows = scorecard.cycle_scorecard(polls, pd.read_csv(res_path))
    path_by_poll = {q["poll_id"]: q["pollster_path"] for q in all_polls}
    for r in cycle_rows:
        r["pollster_path"] = path_by_poll.get(r["poll_id"])
    mk_ctx = markets_context(markets, averages)

    # client-side finder index
    index = []
    for sm in summaries:
        r, a = sm["race"], sm["avg"]
        if a.values:
            if r.kind == "primary":
                top = sorted(((c, v) for c, v in a.values.items() if c != "Other/Undecided"), key=lambda kv: -kv[1])[:3]
                summ = " · ".join(f"{short_name(c)} {v:.1f}%" for c, v in top)
            else:
                summ = " · ".join(f"{short_name(c)} {a.values[c]:.1f}%" for c in r.candidates if c in a.values)
        else:
            summ = "No polls yet"
        index.append(dict(t=r.title, u=sm["path"], k="Average", s=summ,
                          q=" ".join([r.title, r.short_title, r.description] + r.candidates + [short_name(c) for c in r.candidates])))
    index += [
        dict(t="Pollster scorecard", u="/pollsters/", k="Scorecard", s="Which pollster is most accurate? Error, bias and call rate for 60+ pollsters", q="pollster accuracy accurate bias rating grade scorecard most accurate pollsters"),
        dict(t="Prediction markets", u="/markets/", k="Markets", s="Polymarket odds vs. the polls", q="odds betting polymarket kalshi prediction market chance probability favourite favorite"),
        dict(t="Days until the 2028 election", u="/countdown/", k="Countdown", s=f"{(config.ELECTION_DAY_2028 - as_of).days} days to November 7, 2028", q="countdown days until when is election day date 2028 november 7 midterms 2026"),
        dict(t="2028 election calendar", u="/2028/calendar/", k="Calendar", s="Primaries, conventions, Election Day, inauguration", q="calendar schedule primary dates super tuesday convention iowa new hampshire inauguration"),
        dict(t="Methodology", u="/methodology/", k="About", s="How the polling average is computed", q="methodology method how weighted average half-life sample size house effects"),
        dict(t="Open data & API", u="/data/", k="Data", s="Download every poll as CSV or JSON", q="data download csv json api dataset"),
        dict(t="About ElectionsUSA", u="/about/", k="About", s="Who runs ElectionsUSA and how it is funded", q="about contact who funding independent editor"),
        dict(t="Corrections log", u="/corrections/", k="About", s="Every correction, with the old and new value; report an error", q="correction corrections error report mistake wrong fix changed"),
    ]
    # one figure for "a typical poll's error" everywhere it is quoted
    field_error = pollsters.field_error(scorecard.load_538()[0])
    env.globals["field_error"] = field_error
    index += build_pollsters(render, pollster_pages, sc_rows, cycle_rows, as_of, field_error)
    states, nation = history.load()
    index += build_states(render, dist, states, nation, as_of)
    index += build_map_builder(render, dist, states, nation, as_of)
    index += build_midterm_hub(render, averages, states, as_of)
    index += build_2028_hubs(render, summaries, race_lastmod, as_of)
    acc_finder, analysis_feed = build_accuracy_and_analysis(render, dist, polls, averages, pollster_path, as_of)
    index += acc_finder
    (dist / "api" / "search-index.json").write_text(json.dumps(index, ensure_ascii=False))

    (dist / "og" / "site.png").write_bytes(og_cards.site_image(summaries, as_of))
    # capped like race pages: a build for an earlier --as-of date must not claim a future lastmod
    markets_lastmod = max((m["latest"] for m in mk_ctx if m["latest"]), default=None)
    markets_lastmod = min(markets_lastmod, as_of) if markets_lastmod else None
    data_lastmod = max((d for d in [*race_lastmod.values(), markets_lastmod] if d), default=None)

    map_year = max(nation)
    result = accuracy.load_result()
    head = home_head(as_of, bool(cycle_rows) or bool(result and result.as_of <= as_of))
    rated_paths = {p.rated.pollster: p.path for p in pollster_pages.values() if p.rated}
    render("index.html", "/", summaries=summaries, latest=all_polls[:12], markets=mk_ctx[:1],
           scorecard=sc_rows[:8], pollster_paths=rated_paths, head=head, title=head["title"], description=head["description"], lastmod=data_lastmod,
           usmap=usmap.map_context(states, map_year), evbar=usmap.ev_bar(nation[map_year]),
           states=[dict(name=st.name, path=st.path, cls=usmap.shade(st.latest.margin)) for st in states.values()])
    render("scorecard.html", "/pollsters/", rows=sc_rows, cycle_rows=cycle_rows, pollster_paths=rated_paths,
           active=sorted((p for p in pollster_pages.values() if not p.rated), key=lambda p: -len(p.polls)),
           lastmod=min(config.PAGE_REVISED["scorecard"], as_of), title="Pollster Scorecard: Accuracy and Bias Ratings", description="How accurate has each U.S. pollster been? Mean error, partisan bias and call accuracy for 60+ pollsters, recomputed from 11,000 polls matched to results, plus FiveThirtyEight's final grades.")
    render("markets.html", "/markets/", markets=mk_ctx, stale_snapshots=check_data.STALE_PRICE_SNAPSHOTS, kalshi_url=config.KALSHI_URL, title="2028 Election Odds: Prediction Markets vs. Polls",
           description="Polymarket odds for the 2028 presidential election and party nominations, compared with the polling average.",
           lastmod=markets_lastmod)
    render("countdown.html", "/countdown/", lastmod=as_of, title="How Many Days Until the 2028 Election?",
           description=f"Live countdown to the November 7, 2028 U.S. presidential election, with the 2026 midterm date and the 2028 primary calendar.")
    cal_answer = ("South Carolina holds the first 2028 Democratic primary on January 22, 2028, followed by Nevada, New Hampshire, "
                  "New Mexico, Michigan and Virginia in February, under the calendar the DNC approved on August 15, 2026. "
                  "Republicans plan to start in Iowa, but no Republican dates are set. Super Tuesday is March 7, 2028.")
    render("calendar.html", "/2028/calendar/", calendar=config.PRIMARY_CALENDAR_2028, answer=cal_answer, checked=config.CALENDAR_CHECKED,
           title="2028 Primary Calendar: South Carolina Votes First on Jan 22", description=cal_answer,
           lastmod=min(datetime.strptime(config.CALENDAR_CHECKED, "%B %d, %Y").date(), as_of))
    render("methodology.html", "/methodology/", lastmod=min(config.PAGE_REVISED["methodology"], as_of), title="Methodology: How Our Polling Average Works",
           description="A plain-English, fully reproducible description of the ElectionsUSA polling average, pollster weights and scorecard.")
    render("about.html", "/about/", lastmod=min(config.PAGE_REVISED["about"], as_of), title="About ElectionsUSA", description="Who runs ElectionsUSA, how it is funded, and how to report an error.",
           editor=config.SITE["editor"], report_url=config.SITE["issues_url"])
    corrections = pd.read_csv(config.DATA_DIR / "corrections.csv").fillna("").sort_values("date", ascending=False)
    rows = [dict(r, date_label=datetime.strptime(r["date"], "%Y-%m-%d").strftime("%b %-d, %Y")) for r in corrections.to_dict("records")]
    render("corrections.html", "/corrections/", corrections=rows, report_url=config.SITE["issues_url"],
           title="Corrections Log", description="Every material correction to ElectionsUSA's numbers and claims: date, page, old value and new value.",
           lastmod=min(datetime.strptime(corrections["date"].max(), "%Y-%m-%d").date(), as_of))
    corrections.to_csv(dist / "data" / "corrections.csv", index=False)
    terms_date = datetime.strptime(config.SITE["terms_updated"], "%B %d, %Y").date()
    render("terms.html", "/terms/", report_url=config.SITE["issues_url"], terms_updated=config.SITE["terms_updated"],
           title="Terms of Use", description="How you may reuse ElectionsUSA's data and charts, and what the site does and doesn't promise.",
           lastmod=min(terms_date, as_of))
    render("privacy.html", "/privacy/", title="Privacy Policy", description="How ElectionsUSA uses cookies, advertising and analytics.",
           lastmod=min(datetime.strptime(config.SITE["privacy_updated"], "%B %d, %Y").date(), as_of))
    # the published file holds every population of every poll (the averages use one; see dedupe)
    raw_polls = pd.read_csv(config.DATA_DIR / "polls.csv") if (config.DATA_DIR / "polls.csv").exists() else pd.DataFrame(columns=POLL_COLUMNS)
    render("data.html", "/data/", title="Open Data: Download Every Poll", description="Download the full ElectionsUSA polls and prediction-market datasets as CSV and JSON.",
           n_polls=int(raw_polls["poll_id"].nunique()), n_rows=len(raw_polls), n_markets=int(((markets["platform"] == "polymarket") & (markets["source_type"] == "api")).sum()) if not markets.empty else 0,
           lastmod=data_lastmod, lastmod_iso=(data_lastmod or as_of).isoformat(), lastmod_label=(data_lastmod or as_of).strftime("%B %-d, %Y"))
    render("404.html", "/404.html", title="Page not found", description="")

    # data downloads + sitemap/robots
    if (config.DATA_DIR / "polls.csv").exists():
        shutil.copy(config.DATA_DIR / "polls.csv", dist / "data" / "polls.csv")
    # only prices we read from Polymarket's public API; hand-entered press quotes and Kalshi prices are not republished
    if not markets.empty:
        markets[(markets["platform"] == "polymarket") & (markets["source_type"] == "api")].to_csv(dist / "data" / "markets.csv", index=False)
    (dist / "data" / "pollster-scorecard.csv").write_text(pd.DataFrame([asdict(r) for r in sc_rows]).to_csv(index=False))
    base = config.SITE["url"]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p, mod in pages:
        sm.append(f"  <url><loc>{base}{p}</loc>{f'<lastmod>{mod.isoformat()}</lastmod>' if mod else ''}</url>")
    sm.append("</urlset>")
    (dist / "sitemap.xml").write_text("\n".join(sm))
    (dist / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    feed_entries = [dict(title=s["race"].title, path=s["path"], updated=race_lastmod[s["race"].id], summary=answers[s["race"].id])
                    for s in summaries if race_lastmod.get(s["race"].id) and answers.get(s["race"].id)]
    feed_entries += analysis_feed
    feed_entries.append(dict(title="Corrections log", path="/corrections/", updated=min(datetime.strptime(corrections["date"].max(), "%Y-%m-%d").date(), as_of),
                             summary="Every material correction to ElectionsUSA's numbers and claims."))
    build_machine_files(dist, summaries, race_lastmod, answers, feed_entries, as_of)
    (dist / "CNAME").write_text(config.SITE["domain"] + "\n")
    (dist / f"{config.INDEXNOW_KEY}.txt").write_text(config.INDEXNOW_KEY)
    if config.SITE["adsense_client"]:  # ads.txt only for a site that actually sells ads
        pub = config.SITE["adsense_client"].removeprefix("ca-")
        (dist / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")
    (dist / ".nojekyll").write_text("")
    print(f"built {len(pages)} pages -> {dist}")
    return dist


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(), default=None)
    args = ap.parse_args(argv)
    build(args.as_of)
    return 0


if __name__ == "__main__":
    sys.exit(main())
