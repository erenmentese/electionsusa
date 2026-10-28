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
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import average, charts, config, scorecard
from .schema import MARKET_COLUMNS, POLL_COLUMNS, validate_polls

NAV = [
    ("Approval", "/approval/trump/"),
    ("2028 President", "/2028/president/vance-vs-newsom/"),
    ("Dem Primary", "/2028/democratic-primary/"),
    ("GOP Primary", "/2028/republican-primary/"),
    ("Markets", "/markets/"),
    ("Pollsters", "/pollsters/"),
    ("Data", "/data/"),
]


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


def short_name(c: str) -> str:
    return c.split()[-1] if c not in ("Other/Undecided", "Approve", "Disapprove", "Democrats", "Republicans") else c


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    polls_path = config.DATA_DIR / "polls.csv"
    polls = validate_polls(pd.read_csv(polls_path)) if polls_path.exists() else pd.DataFrame(columns=POLL_COLUMNS)
    mpath = config.DATA_DIR / "markets.csv"
    markets = pd.read_csv(mpath) if mpath.exists() else pd.DataFrame(columns=MARKET_COLUMNS)
    _, ratings = scorecard.load_538()
    return polls, markets, ratings


def race_table(ra: average.RaceAverage, race: config.Race, ratings: pd.DataFrame) -> list[dict]:
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
        rows.append(dict(
            pollster=r["pollster"], sponsor=r["sponsor"] if isinstance(r["sponsor"], str) else "",
            dates=fmt_dates(r["start_date"], r["end_date"]), end_date=r["end_date"].isoformat(),
            sample=fmt_sample(r["sample_size"], r["population"]),
            grade=average.pollster_grade(r["pollster"], grades) or "—",
            weight=round(float(w.loc[i]), 1) if len(w) else 0.0,
            vals=vals, margin=margin,
            margin_label=signed(margin, short_name(race.candidates[0]), short_name(race.candidates[1])) if margin is not None else "—",
            source_url=r["source_url"] if isinstance(r["source_url"], str) else "",
            notes=r["notes"] if isinstance(r["notes"], str) else "",
        ))
    return rows


def race_colors(race: config.Race) -> dict[str, str]:
    return {c: config.PARTY_COLORS.get(race.parties.get(c, "OTHER"), "#6b7280") for c in race.candidates}


def race_charts(ra: average.RaceAverage, race: config.Race) -> dict[str, str]:
    colors = race_colors(race)
    wide = ra.polls if ra.polls is not None else pd.DataFrame()
    points = {c: [(r["end_date"], float(r[c])) for _, r in wide.iterrows() if pd.notna(r[c])] for c in race.candidates} if not wide.empty else {}
    if race.kind == "primary":
        top = sorted(ra.values, key=ra.values.get, reverse=True)[:5]
        # distinct shades for same-party candidates
        palette = ["#1e3a8a", "#0f766e", "#5b21b6", "#9f1239", "#9a3412", "#52525b"] if race.parties.get(top[0] if top else "", "DEM") == "DEM" \
            else ["#991b1b", "#9a3412", "#854d0e", "#5b21b6", "#0f766e", "#52525b"]
        pc = {c: palette[i % len(palette)] for i, c in enumerate(top)}
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


def latest_polls(polls: pd.DataFrame, n: int = 12) -> list[dict]:
    if polls.empty:
        return []
    out = []
    for pid, g in polls.groupby("poll_id"):
        race = config.RACE_BY_ID.get(g["race_id"].iat[0])
        if not race:
            continue
        vals = dict(zip(g["candidate"], g["pct"]))
        ordered = [c for c in race.candidates if c in vals]
        if race.kind == "primary":
            ordered = sorted((c for c in ordered if c != "Other/Undecided"), key=lambda c: -vals[c])[:3]
        headline = "  ·  ".join(f"{short_name(c)} {vals[c]:g}%" for c in ordered)
        out.append(dict(race=race, pollster=g["pollster"].iat[0], end_date=g["end_date"].iat[0],
                        dates=fmt_dates(g["start_date"].iat[0], g["end_date"].iat[0]),
                        headline=headline, source_url=g["source_url"].iat[0]))
    out.sort(key=lambda d: d["end_date"], reverse=True)
    return out[:n]


def markets_context(markets: pd.DataFrame, averages: dict[str, average.RaceAverage]) -> list[dict]:
    out = []
    if markets.empty:
        return out
    markets = markets.copy()
    markets["snapshot_date"] = pd.to_datetime(markets["snapshot_date"]).dt.date
    for mk in config.MARKETS:
        sub = markets[markets["market_id"] == mk["id"]]
        if sub.empty:
            out.append(dict(market=mk, rows=[], chart="", latest=None, note="No snapshot yet. The pipeline records one on each run."))
            continue
        latest_by_platform = {}
        for platform, g in sub.groupby("platform"):
            d = g["snapshot_date"].max()
            snap = g[g["snapshot_date"] == d].sort_values("price", ascending=False)
            latest_by_platform[platform] = (d, snap)
        outcomes = sorted({o for _, (_, s) in latest_by_platform.items() for o in s["outcome"]},
                          key=lambda o: -max(float(s[s["outcome"] == o]["price"].max()) if (s["outcome"] == o).any() else 0 for _, (_, s) in latest_by_platform.items()))
        rows = []
        for o in outcomes:
            row = {"outcome": o}
            for p in ("polymarket", "kalshi"):
                if p in latest_by_platform:
                    s = latest_by_platform[p][1]
                    v = s[s["outcome"] == o]["price"]
                    row[p] = float(v.iat[0]) if len(v) else None
                else:
                    row[p] = None
            rows.append(row)
        chart = ""
        cmp_race = mk.get("compare_race")
        if cmp_race and cmp_race in averages and averages[cmp_race].values:
            av = averages[cmp_race].values
            groups = {}
            for o in outcomes[:8]:
                g = {}
                for p in ("polymarket", "kalshi"):
                    v = next((r[p] for r in rows if r["outcome"] == o), None)
                    if v is not None:
                        g[p.capitalize()] = v
                if o in av:
                    g["Poll average"] = av[o]
                groups[o] = g
            chart = charts.grouped_bars(groups, {"Poll average": "#111827", "Polymarket": "#2563eb", "Kalshi": "#16a34a"},
                                        title=f"{mk['title']}: polls vs. prediction markets", chart_id=f"cmp-{mk['id']}")
        latest = max(d for d, _ in latest_by_platform.values())
        notes = sorted({n for n in sub["notes"].dropna().astype(str) if n})
        out.append(dict(market=mk, rows=rows, chart=chart, latest=latest, note="; ".join(notes)))
    return out


# ------------------------------------------------------------------- build
def build(as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    polls, markets, ratings = load_data()
    env = Environment(loader=FileSystemLoader(str(config.TEMPLATE_DIR)), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["signed"] = signed
    env.filters["short"] = short_name
    env.globals.update(site=config.SITE, nav=NAV, build_date=as_of.strftime("%B %-d, %Y"),
                       build_iso=as_of.isoformat(), year=as_of.year,
                       election_day=config.ELECTION_DAY_2028, midterm_day=config.MIDTERM_DAY_2026,
                       days_to_election=(config.ELECTION_DAY_2028 - as_of).days,
                       days_to_midterm=(config.MIDTERM_DAY_2026 - as_of).days,
                       races=config.RACES)

    dist = config.DIST_DIR
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    shutil.copytree(config.STATIC_DIR, dist / "static")
    (dist / "api").mkdir()
    (dist / "data").mkdir()
    pages: list[str] = []

    def render(template: str, out_path: str, **ctx) -> None:
        html = env.get_template(template).render(path=out_path, **ctx)
        target = dist / out_path.strip("/") / "index.html" if out_path != "/" else dist / "index.html"
        if out_path.endswith(".html"):
            target = dist / out_path.strip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        if not out_path.endswith(".html"):
            pages.append(out_path)

    averages: dict[str, average.RaceAverage] = {}
    summaries = []
    for race in config.RACES:
        ra = average.compute_race(polls, race, ratings, as_of=as_of)
        averages[race.id] = ra
        table = race_table(ra, race, ratings)
        ch = race_charts(ra, race)
        summaries.append(dict(race=race, avg=ra, colors=race_colors(race), path=f"/{race.slug}/"))
        shown = [c for c in race.candidates if any(r["vals"].get(c) is not None for r in table)
                 and (race.kind != "primary" or c != "Other/Undecided")]
        render("race.html", f"/{race.slug}/", race=race, avg=ra, table=table, charts=ch, colors=race_colors(race),
               shown=shown, title=race.title, description=race.description)
        api = dict(race_id=race.id, title=race.title, as_of=as_of.isoformat(), method="https://electionsusa.org/methodology/",
                   average=ra.values, margin=ra.margin, n_polls_weighted=ra.n_polls, n_polls_total=ra.n_polls_total,
                   trend={c: [(d.isoformat(), v) for d, v in s] for c, s in ra.trend.items()},
                   polls=[{k: v for k, v in row.items()} for row in table])
        (dist / "api" / f"{race.id}.json").write_text(json.dumps(api, indent=1, default=str))

    sc_rows = scorecard.historical_scorecard()
    cycle_rows = []
    res_path = config.DATA_DIR / "results" / "2026.csv"
    if res_path.exists():
        cycle_rows = scorecard.cycle_scorecard(polls, pd.read_csv(res_path))
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
        dict(t="Prediction markets", u="/markets/", k="Markets", s="Polymarket and Kalshi odds vs. the polls", q="odds betting polymarket kalshi prediction market chance probability favourite favorite"),
        dict(t="Days until the 2028 election", u="/countdown/", k="Countdown", s=f"{(config.ELECTION_DAY_2028 - as_of).days} days to November 7, 2028", q="countdown days until when is election day date 2028 november 7 midterms 2026"),
        dict(t="2028 election calendar", u="/2028/calendar/", k="Calendar", s="Primaries, conventions, Election Day, inauguration", q="calendar schedule primary dates super tuesday convention iowa new hampshire inauguration"),
        dict(t="Methodology", u="/methodology/", k="About", s="How the polling average is computed", q="methodology method how weighted average half-life sample size house effects"),
        dict(t="Open data & API", u="/data/", k="Data", s="Download every poll as CSV or JSON", q="data download csv json api dataset"),
        dict(t="About & corrections", u="/about/", k="About", s="Who runs ElectionsUSA and how to report an error", q="about contact who correction error report funding ads independent"),
    ]
    for pr in sc_rows[:40]:
        index.append(dict(t=pr.pollster, u="/pollsters/", k="Pollster", s=f"Avg error {pr.mean_abs_error}, bias {pr.bias_label}, {pr.n_polls} polls", q=f"{pr.pollster} pollster accuracy"))
    (dist / "api" / "search-index.json").write_text(json.dumps(index, ensure_ascii=False))

    render("index.html", "/", summaries=summaries, latest=latest_polls(polls), markets=mk_ctx[:1],
           scorecard=sc_rows[:8], title=None, description=config.SITE["description"])
    render("scorecard.html", "/pollsters/", rows=sc_rows, cycle_rows=cycle_rows,
           title="Pollster Scorecard: Accuracy and Bias Ratings", description="How accurate has each U.S. pollster been? Mean error, partisan bias and call accuracy for 60+ pollsters, recomputed from 11,000 polls matched to results, plus FiveThirtyEight's final grades.")
    render("markets.html", "/markets/", markets=mk_ctx, title="2028 Election Odds: Prediction Markets vs. Polls",
           description="Polymarket and Kalshi odds for the 2028 presidential election and party nominations, compared with the polling average.")
    render("countdown.html", "/countdown/", title="How Many Days Until the 2028 Election?",
           description=f"Live countdown to the November 7, 2028 U.S. presidential election, with the 2026 midterm date and the 2028 primary calendar.")
    render("calendar.html", "/2028/calendar/", calendar=config.PRIMARY_CALENDAR_2028, title="2028 Election Calendar: Primaries, Conventions, Election Day",
           description="Key dates for the 2028 U.S. presidential election cycle.")
    render("methodology.html", "/methodology/", title="Methodology: How Our Polling Average Works",
           description="A plain-English, fully reproducible description of the ElectionsUSA polling average, pollster weights and scorecard.")
    render("about.html", "/about/", title="About ElectionsUSA", description="Who runs ElectionsUSA, how it is funded, and how to report an error.")
    render("privacy.html", "/privacy/", title="Privacy Policy", description="How ElectionsUSA uses cookies, advertising and analytics.")
    render("data.html", "/data/", title="Open Data: Download Every Poll", description="Download the full ElectionsUSA polls and prediction-market datasets as CSV and JSON.",
           n_polls=int(polls["poll_id"].nunique()) if not polls.empty else 0, n_rows=len(polls), n_markets=len(markets))
    render("404.html", "/404.html", title="Page not found", description="")

    # data downloads + sitemap/robots
    for f in ("polls.csv", "markets.csv"):
        src = config.DATA_DIR / f
        if src.exists():
            shutil.copy(src, dist / "data" / f)
    (dist / "data" / "pollster-scorecard.csv").write_text(pd.DataFrame([asdict(r) for r in sc_rows]).to_csv(index=False))
    base = config.SITE["url"]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        sm.append(f"  <url><loc>{base}{p}</loc><lastmod>{as_of.isoformat()}</lastmod></url>")
    sm.append("</urlset>")
    (dist / "sitemap.xml").write_text("\n".join(sm))
    (dist / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    (dist / "CNAME").write_text(config.SITE["domain"] + "\n")
    (dist / "ads.txt").write_text("# Replace with the line Google AdSense gives you, e.g.\n# google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0\n")
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
