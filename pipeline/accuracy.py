"""How close the final 2026 generic-ballot polls came to the national House popular vote.

The result lives in data/results/2026-house-national.json, entered by hand from a cited count:

    {"dem_pct": 51.2, "rep_pct": 46.9, "status": "preliminary", "counted_pct": 92,
     "as_of": "2026-11-05", "source": "The Associated Press vote count", "source_url": "https://..."}

`status` is "preliminary" (unofficial count, still moving) or "certified". Until the file exists every
page that uses it says the result is pending and shows no error figures.

Each poll in the final three weeks (21 days up to Election Day) is scored on the Democratic-minus-
Republican margin: error = |poll margin - result margin|, bias = poll margin - result margin, so a
positive bias means the poll was more favourable to Democrats than the result (shown "D+").
One population per poll (see dedupe), polls credited to the firm that ran them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from . import config, pollsters

RACE = "generic-ballot-2026"
WINDOW_DAYS = 21
RESULT_PATH = config.DATA_DIR / "results" / "2026-house-national.json"


@dataclass
class Result:
    dem_pct: float
    rep_pct: float
    status: str
    counted_pct: float | None
    as_of: date
    source: str
    source_url: str

    @property
    def margin(self) -> float:
        return round(self.dem_pct - self.rep_pct, 1)

    @property
    def preliminary(self) -> bool:
        return self.status != "certified"


def load_result(path=RESULT_PATH) -> Result | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    return Result(dem_pct=float(d["dem_pct"]), rep_pct=float(d["rep_pct"]), status=d.get("status", "preliminary"),
                  counted_pct=float(d["counted_pct"]) if d.get("counted_pct") is not None else None,
                  as_of=datetime.strptime(d["as_of"], "%Y-%m-%d").date(), source=d["source"], source_url=d["source_url"])


def final_polls(polls: pd.DataFrame) -> list[dict]:
    """Generic-ballot polls that ended in the final three weeks, one row each, newest first."""
    sub = polls[polls["race_id"] == RACE]
    if sub.empty:
        return []
    start = config.MIDTERM_DAY_2026 - timedelta(days=WINDOW_DAYS)
    out = []
    for pid, g in sub.groupby("poll_id"):
        r = g.iloc[0]
        if not (start <= r["end_date"] <= config.MIDTERM_DAY_2026):
            continue
        vals = dict(zip(g["candidate"], g["pct"]))
        if "Democrats" not in vals or "Republicans" not in vals:
            continue
        sponsor = r["sponsor"] if isinstance(r["sponsor"], str) else ""
        out.append(dict(poll_id=pid, pollster=pollsters.firm(r["pollster"], sponsor) or r["pollster"], listed=r["pollster"],
                        sponsor=sponsor, end_date=r["end_date"], population=r["population"], sample_size=r["sample_size"],
                        dem=float(vals["Democrats"]), rep=float(vals["Republicans"]),
                        margin=round(float(vals["Democrats"]) - float(vals["Republicans"]), 1),
                        source_url=r["source_url"] if isinstance(r["source_url"], str) else ""))
    return sorted(out, key=lambda p: p["end_date"], reverse=True)


def score(polls: list[dict], result: Result | None) -> list[dict]:
    """One row per pollster: its final-three-weeks polls and, with a result, their mean error and bias.
    Sorted by error when there is a result, otherwise by the number of polls."""
    by: dict[str, list[dict]] = {}
    for p in polls:
        by.setdefault(p["pollster"], []).append(p)
    rows = []
    for name, ps in by.items():
        margin = round(sum(p["margin"] for p in ps) / len(ps), 1)
        row = dict(pollster=name, n=len(ps), last_end=max(p["end_date"] for p in ps), margin=margin, error=None, bias=None)
        if result:
            errs = [p["margin"] - result.margin for p in ps]
            row["bias"] = round(sum(errs) / len(errs), 1)
            row["error"] = round(sum(abs(e) for e in errs) / len(errs), 1)
        rows.append(row)
    if result:
        return sorted(rows, key=lambda r: (r["error"], -r["n"], r["pollster"]))
    return sorted(rows, key=lambda r: (-r["n"], r["pollster"]))


def fmt_margin(m: float) -> str:
    return "even" if abs(m) < 0.05 else f"{'D' if m > 0 else 'R'}+{abs(m):.1f}"


def bias_label(b: float | None) -> str:
    if b is None:
        return "pending"
    if abs(b) < 0.05:
        return "none"
    return f"{'D' if b > 0 else 'R'}+{abs(b):.1f}"


def answer(rows: list[dict], result: Result | None, final_margin: float | None, min_polls: int = 2) -> str:
    """The one-sentence answer at the top of /2026/pollster-accuracy/."""
    if not result:
        return ("The national House popular vote is still being counted, so no 2026 generic-ballot pollster can be scored yet. "
                f"{len(rows)} pollsters published polls in the final three weeks; this page scores each of them as soon as a count is available.")
    label = "preliminary " if result.preliminary else ""
    count = f" with {result.counted_pct:.0f}% of the expected vote counted" if result.counted_pct is not None and result.preliminary else ""
    eligible = [r for r in rows if r["n"] >= min_polls] or rows
    best = eligible[0]
    avg = (f" The final ElectionsUSA average was {fmt_margin(final_margin)} against a result of "
           f"{fmt_margin(result.margin)}.") if final_margin is not None else ""
    return (f"{best['pollster']} was the most accurate generic-ballot pollster of 2026 on the {label}House popular vote{count}, "
            f"missing the margin by {best['error']:.1f} points on average across {best['n']} final-three-weeks poll"
            f"{'s' if best['n'] != 1 else ''} (as of {result.as_of.strftime('%B %-d, %Y')}).{avg}")
