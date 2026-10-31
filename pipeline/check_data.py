"""Health check for the scheduled data workflow: is the site still being fed?

Runs after each fetch and asks: did the fetch step work, did the tests pass, are the
fast-moving series still getting new polls, is there a fresh market snapshot, and does the
raw CSV hold rows the site would silently drop (a sign the Wikipedia parser broke).
Writes a Markdown report and exits 1 when a human should look; the workflow turns that into
a GitHub issue and closes it again once everything is healthy.

    python -m pipeline.check_data --report health.md --fetch success --tests success
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import config
from .schema import validate_polls

# Days without a new poll before we alarm. Hypothetical general-election matchups are polled
# too rarely to alarm on; the generic ballot stops being polled once the midterm is over.
STALE_AFTER = {"approval": 7, "generic": 10, "primary": 30}
MARKETS_STALE_AFTER = 2
TWO_WAY = ("general", "generic", "approval")


def structure(polls_raw: pd.DataFrame, today: date) -> list[str]:
    """Problems with the data itself, as opposed to its freshness. The test suite fails on
    these, so a broken parse is never committed; staleness only raises the alert."""
    problems = []
    pct = pd.to_numeric(polls_raw["pct"], errors="coerce")
    ends = pd.to_datetime(polls_raw["end_date"], errors="coerce")
    unusable = int((pct.isna() | (pct < 0) | (pct > 100) | ends.isna()).sum())
    if unusable:
        problems.append(f"{unusable} row(s) in polls.csv have a missing or impossible percentage or date and are hidden from the site.")
    unknown = sorted(set(polls_raw["race_id"].dropna()) - set(config.RACE_BY_ID))
    if unknown:
        problems.append(f"polls.csv has rows for races the site doesn't know: {', '.join(unknown)}.")

    polls = validate_polls(polls_raw)
    future = polls[polls["end_date"] > today + timedelta(days=1)]
    if len(future):
        problems.append(f"{future['poll_id'].nunique()} poll(s) end in the future (latest {future['end_date'].max()}), likely a date-parsing error.")
    two_way = polls[polls["race_id"].map(lambda r: getattr(config.RACE_BY_ID.get(r), "kind", "") in TWO_WAY)]
    sums = two_way.groupby("poll_id")["pct"].sum()
    if (sums > 105).any():
        problems.append(f"{int((sums > 105).sum())} two-way poll(s) add up to more than 105%, likely a column mix-up in parsing.")
    return problems


def check(polls_raw: pd.DataFrame, markets: pd.DataFrame, today: date,
          fetch: str = "success", tests: str = "success") -> tuple[list[str], list[str]]:
    """Return (problems, status lines). No problems means healthy."""
    problems, status = [], []
    if fetch == "failure":
        problems.append("The fetch step failed (see the workflow log); the site is serving the last good data.")
    if tests == "failure":
        problems.append("Tests failed, so this run's data was not committed or deployed.")
    problems += structure(polls_raw, today)

    polls = validate_polls(polls_raw)
    for race in config.RACES:
        sub = polls[polls["race_id"] == race.id]
        latest = sub["end_date"].max() if len(sub) else None
        age = (today - latest).days if latest else None
        status.append(f"{race.short_title}: " + (f"latest poll ended {latest} ({age} days ago)" if latest else "no polls"))
        limit = STALE_AFTER.get(race.kind)
        if race.kind == "generic" and today > config.MIDTERM_DAY_2026:
            limit = None
        if limit and (age is None or age > limit):
            problems.append(f"No new {race.short_title} poll for {age if age is not None else 'ever'} days (alert after {limit}).")

    snap = pd.to_datetime(markets["snapshot_date"], errors="coerce").dt.date.max() if len(markets) else None
    status.append(f"Markets: latest snapshot {snap}" if snap else "Markets: no snapshots")
    if snap is None or (today - snap).days > MARKETS_STALE_AFTER:
        problems.append(f"No prediction-market snapshot since {snap} (alert after {MARKETS_STALE_AFTER} days).")
    return problems, status


def report(problems: list[str], status: list[str], now: datetime) -> str:
    head = "All good" if not problems else f"{len(problems)} problem{'s' if len(problems) != 1 else ''}"
    lines = [f"## Data health: {head}", f"Checked {now:%Y-%m-%d %H:%M} UTC.", ""]
    if problems:
        lines += ["### Needs attention"] + [f"- {p}" for p in problems] + [""]
    lines += ["### Latest data"] + [f"- {s}" for s in status]
    run = os.environ.get("GITHUB_RUN_ID")
    if run:
        lines += ["", f"[Workflow run]({os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run})"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="health.md")
    ap.add_argument("--fetch", default="success", help="outcome of the fetch step")
    ap.add_argument("--tests", default="success", help="outcome of the test step")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    polls = pd.read_csv(config.DATA_DIR / "polls.csv")
    markets = pd.read_csv(config.DATA_DIR / "markets.csv")
    problems, status = check(polls, markets, now.date(), args.fetch, args.tests)
    text = report(problems, status, now)
    print(text)
    with open(args.report, "w") as f:
        f.write(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
