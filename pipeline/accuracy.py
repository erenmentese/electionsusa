"""How close the final 2026 generic-ballot polls came to the national House popular vote.

The result lives in data/results/2026-house-national.json, entered by hand from a cited count:

    {"dem_pct": 51.2, "rep_pct": 46.9, "status": "preliminary", "counted_pct": 92,
     "as_of": "2026-11-05T15:00Z", "source": "The Associated Press vote count", "source_url": "https://...",
     "history": [{"dem_pct": 51.6, "rep_pct": 46.5, "counted_pct": 85, "as_of": "2026-11-04T16:00Z",
                  "source": "...", "source_url": "https://..."}]}

`status` is "preliminary" (unofficial count, still moving) or "certified". `as_of` is a UTC time
("2026-11-05T15:00Z") or a date. `history` is optional: earlier counts, oldest first, so the page can
show how the margin moved as late ballots were counted. Until the file exists every page that uses it
says the result is pending and shows no error figures. A malformed file fails the build (and so the
tests) with a message saying what is wrong, so a bad count never reaches the site.

We never call races and never name "the most accurate pollster" from an early count: below
NAME_MIN_COUNTED percent of the expected vote no pollster is named, and while the count is preliminary
the leader is "closest so far".

Each poll in the final three weeks (21 days up to Election Day) is scored on the Democratic-minus-
Republican margin: error = |poll margin - result margin|, bias = poll margin - result margin, so a
positive bias means the poll was more favourable to Democrats than the result (shown "D+").
One population per poll (see dedupe), polls credited to the firm that ran them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from . import config, pollsters

RACE = "generic-ballot-2026"
WINDOW_DAYS = 21
RESULT_PATH = config.DATA_DIR / "results" / "2026-house-national.json"
NAME_MIN_COUNTED = 80  # percent of the expected vote counted before a pollster is named
STATUSES = ("preliminary", "certified")
ET = ZoneInfo("America/New_York")


@dataclass
class Count:
    """One published national count: the current one, or an earlier one kept in `history`."""
    dem_pct: float
    rep_pct: float
    counted_pct: float | None
    as_of: date
    source: str
    source_url: str
    as_of_at: datetime | None = None  # UTC, when the file gives a time

    @property
    def margin(self) -> float:
        return round(self.dem_pct - self.rep_pct, 1)

    @property
    def iso(self) -> str:
        return self.as_of_at.strftime("%Y-%m-%dT%H:%MZ") if self.as_of_at else self.as_of.isoformat()

    def _at(self, day: str) -> str:
        if not self.as_of_at:
            return self.as_of.strftime(day)
        t = self.as_of_at.astimezone(ET)
        clock = f"{t.hour % 12 or 12}{f':{t.minute:02d}' if t.minute else ''} {'a.m.' if t.hour < 12 else 'p.m.'}"
        return f"{t.strftime(day)}, {clock} ET"

    @property
    def stamp(self) -> str:
        """'November 5, 2026, 10 a.m. ET', or the date alone when no time was given."""
        return self._at("%B %-d, %Y")

    @property
    def short(self) -> str:
        """'Nov 5, 10 a.m. ET', for tables."""
        return self._at("%b %-d")


@dataclass
class Result(Count):
    status: str = "preliminary"
    history: list[Count] = field(default_factory=list)

    @property
    def preliminary(self) -> bool:
        return self.status != "certified"

    @property
    def nameable(self) -> bool:
        """Enough of the vote is counted to say which pollster is closest."""
        return not self.preliminary or (self.counted_pct is not None and self.counted_pct >= NAME_MIN_COUNTED)


def _when(value: str) -> tuple[date, datetime | None]:
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            at = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return at.date(), at
        except ValueError:
            pass
    return datetime.strptime(value, "%Y-%m-%d").date(), None


def _count(d: dict, where: str) -> dict:
    missing = [k for k in ("dem_pct", "rep_pct", "as_of", "source", "source_url") if d.get(k) in (None, "")]
    if missing:
        raise ValueError(f"{where}: missing {', '.join(missing)}")
    dem, rep = float(d["dem_pct"]), float(d["rep_pct"])
    counted = float(d["counted_pct"]) if d.get("counted_pct") is not None else None
    if not (0 < dem < 100 and 0 < rep < 100 and dem + rep <= 100):
        raise ValueError(f"{where}: dem_pct {dem} and rep_pct {rep} must be shares of all House votes")
    if counted is not None and not 0 < counted <= 100:
        raise ValueError(f"{where}: counted_pct {counted} must be between 0 and 100")
    if not str(d["source_url"]).startswith("https://"):
        raise ValueError(f"{where}: source_url must be an https:// link to the published count")
    try:
        day, at = _when(str(d["as_of"]))
    except ValueError:
        raise ValueError(f"{where}: as_of {d['as_of']!r} must look like 2026-11-05T15:00Z or 2026-11-05") from None
    return dict(dem_pct=dem, rep_pct=rep, counted_pct=counted, as_of=day, as_of_at=at,
                source=str(d["source"]), source_url=str(d["source_url"]))


def load_result(path=RESULT_PATH) -> Result | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    status = d.get("status", "preliminary")
    if status not in STATUSES:
        raise ValueError(f"{path.name}: status {status!r} must be one of {', '.join(STATUSES)}")
    history = [Count(**_count(h, f"{path.name} history[{i}]")) for i, h in enumerate(d.get("history") or [])]
    result = Result(**_count(d, path.name), status=status, history=history)
    stamps = [h.iso for h in history] + [result.iso]
    if any(a >= b for a, b in zip(stamps, stamps[1:])):
        raise ValueError(f"{path.name}: history must run oldest first and every entry must be older than the current count ({result.iso})")
    return result


def known_on(result: Result | None, day: date) -> Result | None:
    """The result a build for `day` may show: a build for an earlier date must not know a later count."""
    return result if result and result.as_of <= day else None


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
    Sorted by error once enough of the vote is counted to rank pollsters, otherwise by the number of polls."""
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
    if result and result.nameable:
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


def poll_rows(polls: list[dict], result: Result | None, pollster_path=lambda name: None) -> list[dict]:
    """Every final-three-weeks poll against the result, for the scorecard's 2026 table and each pollster's page."""
    if not result:
        return []
    return [dict(race_id=RACE, race="Generic ballot", poll_id=p["poll_id"], pollster=p["pollster"], pollster_path=pollster_path(p["pollster"]),
                 end_date=p["end_date"], poll_margin=p["margin"], actual_margin=result.margin,
                 error=round(abs(p["margin"] - result.margin), 1), bias=round(p["margin"] - result.margin, 1),
                 # who won the popular vote is only settled by a certified, untied result
                 right_call=None if result.preliminary or result.margin == 0 else (p["margin"] > 0) == (result.margin > 0),
                 preliminary=result.preliminary) for p in polls]


def counted_text(result: Result) -> str:
    """'with about 88% of the expected vote counted, as of November 5, 2026, 10 a.m. ET' (preliminary) or 'as of ...'."""
    pct = f"with about {result.counted_pct:.0f}% of the expected vote counted, " if result.counted_pct is not None and result.preliminary else ""
    return f"{pct}as of {result.stamp}"


def answer(rows: list[dict], result: Result | None, final_margin: float | None, min_polls: int = 2) -> str:
    """The one-sentence answer at the top of /2026/pollster-accuracy/. Only a certified result has a 'most
    accurate' pollster; a preliminary count has one 'closest so far', and an early count names nobody."""
    if not result:
        return ("The national House popular vote is still being counted, so no 2026 generic-ballot pollster can be scored yet. "
                f"{len(rows)} pollsters published polls in the final three weeks; this page scores each of them as soon as a count is available.")
    avg = (f" The final ElectionsUSA average was {fmt_margin(final_margin)} against "
           f"{'a count so far of' if result.preliminary else 'a result of'} {fmt_margin(result.margin)}.") if final_margin is not None else ""
    if not result.nameable:
        return (f"On the early, unofficial count the House popular vote is {fmt_margin(result.margin)} "
                f"({counted_text(result)}).{avg} Pollsters are ranked once most of the vote is counted.")
    best = ([r for r in rows if r["n"] >= min_polls] or rows)[0]
    among = f" among pollsters with at least {min_polls} final-three-weeks polls" if best is not rows[0] else ""
    polls_n = f"{best['n']} final-three-weeks poll{'s' if best['n'] != 1 else ''}"
    if result.preliminary:
        return (f"On the preliminary House popular vote ({counted_text(result)}), {best['pollster']} is the closest "
                f"generic-ballot pollster of 2026 so far{among}, missing the margin by {best['error']:.1f} points on average "
                f"across {polls_n}.{avg} The ranking can change until states certify.")
    return (f"{best['pollster']} was the most accurate generic-ballot pollster of 2026{among} on the certified House popular "
            f"vote, missing the margin by {best['error']:.1f} points on average across {polls_n}.{avg}")
