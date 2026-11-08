"""The week in polls: how each average moved over seven days, and which polls came in.

`python -m pipeline.weekly 2026-11-08` prints the week ending that day as Markdown tables for a weekly note in
content/analysis/. The note quotes these numbers and pastes the tables, so what is published never drifts
from what was written, even if a late poll is added for that week afterwards.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import pandas as pd

from . import average, config
from .build import load_data, short_name, signed

RACES = ("approval-trump-2", "dem-primary-2028", "gop-primary-2028",
         "pres-2028-vance-newsom", "pres-2028-vance-ocasio-cortez", "pres-2028-vance-buttigieg")


def summary(race: config.Race, ra: average.RaceAverage) -> tuple[str, float | None]:
    """('Approve 39.5%', 39.5) for approval, the leader for a primary, the margin for a matchup."""
    if not ra.values:
        return "—", None
    if race.kind == "approval":
        return f"Approve {ra.values['Approve']:.1f}%", ra.values["Approve"]
    if race.kind == "primary":
        lead = max((c for c in ra.values if c != "Other/Undecided"), key=ra.values.get)
        return f"{short_name(lead)} {ra.values[lead]:.1f}%", ra.values[lead]
    return signed(ra.margin, short_name(race.candidates[0]), short_name(race.candidates[1])), ra.margin


def moves(polls: pd.DataFrame, ratings, end: date) -> list[dict]:
    rows = []
    for rid in RACES:
        race = config.RACE_BY_ID[rid]
        now = average.compute_race(polls, race, ratings, as_of=end, trend_step_days=30)
        prev = average.compute_race(polls, race, ratings, as_of=end - timedelta(days=7), trend_step_days=30)
        (now_s, now_v), (prev_s, prev_v) = summary(race, now), summary(race, prev)
        if race.kind == "primary" and now.values and prev.values:  # the leader's own week, even if the lead changed
            lead = max((c for c in now.values if c != "Other/Undecided"), key=now.values.get)
            prev_v = prev.values.get(lead)
        change = None if now_v is None or prev_v is None else round(now_v - prev_v, 1)
        rows.append(dict(race=race, now=now_s, prev=prev_s, change=change, n_polls=now.n_polls))
    return rows


def new_polls(polls: pd.DataFrame, end: date) -> list[dict]:
    """Every poll in the tracked races whose fieldwork ended in the seven days to `end`, newest first."""
    out = []
    for rid in RACES:
        race = config.RACE_BY_ID[rid]
        wide = average.to_wide(polls, race)
        if wide.empty:
            continue
        week = wide[(wide["end_date"] > end - timedelta(days=7)) & (wide["end_date"] <= end)]
        for _, p in week.iterrows():
            vals = {c: p[c] for c in race.candidates if c != "Other/Undecided" and pd.notna(p.get(c))}
            if race.kind == "primary":
                top = sorted(vals, key=vals.get, reverse=True)[:3]
                result = ", ".join(f"{short_name(c)} {vals[c]:g}%" for c in top)
            else:
                result = ", ".join(f"{short_name(c)} {vals[c]:g}%" for c in race.candidates if c in vals)
            out.append(dict(race=race, pollster=p["pollster"], sponsor=p["sponsor"], end_date=p["end_date"],
                            population=p["population"] or "", sample_size=p["sample_size"], result=result,
                            source_url=p["source_url"]))
    return sorted(out, key=lambda r: (r["end_date"], r["race"].id), reverse=True)


def change_label(race: config.Race, x: float | None) -> str:
    """'+0.3' for a share, '2.0 toward Vance' for a matchup margin."""
    if x is None:
        return "—"
    if abs(x) < 0.05:
        return "no change"
    if race.kind in ("approval", "primary"):
        return f"{x:+.1f}"
    return f"{abs(x):.1f} toward {short_name(race.candidates[0] if x > 0 else race.candidates[1])}"


def markdown(polls: pd.DataFrame, ratings, end: date) -> str:
    lines = [f"Week ending {end.strftime('%B %-d, %Y')}", "", "| Average | Now | A week earlier | Change |", "|---|---|---|---|"]
    for r in moves(polls, ratings, end):
        lines.append(f"| [{r['race'].short_title}](/{r['race'].slug}/) | {r['now']} | {r['prev']} | {change_label(r['race'], r['change'])} |")
    lines += ["", "| Poll | Ended | Race | Result |", "|---|---|---|---|"]
    for p in new_polls(polls, end):
        who = p["pollster"] + (f" / {p['sponsor']}" if p["sponsor"] and p["sponsor"] != p["pollster"] else "")
        size = f", {int(p['sample_size']):,} {p['population']}" if pd.notna(p["sample_size"]) else ""
        lines.append(f"| [{who}]({p['source_url']}){size} | {p['end_date'].strftime('%b %-d')} | {p['race'].short_title} | {p['result']} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    end = date.fromisoformat(argv[0]) if argv else date.today()
    polls, _, ratings = load_data()
    print(markdown(polls, ratings, end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
