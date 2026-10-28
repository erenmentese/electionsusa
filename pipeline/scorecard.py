"""Pollster scorecard.

Historical accuracy comes from FiveThirtyEight's open `raw-polls` dataset
(CC BY 4.0; 11,000+ polls, 1998-2022, each matched to the actual result). We
recompute simple, explainable statistics from it rather than copying 538's
proprietary model, and show 538's final (2023) letter grade alongside for
reference.

Sign convention: bias > 0 means the poll overstated the Democrat relative to the
result ("D+"); bias < 0 means it overstated the Republican ("R+").

When `data/results/<year>.csv` exists (columns: race_id, candidate, pct), the
same statistics are computed for that cycle's polls in data/polls.csv, which is
how the 2026 midterm scorecard gets built after November 3, 2026.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from . import config


@dataclass
class PollsterRow:
    pollster: str
    n_polls: int
    cycles: str
    mean_abs_error: float
    adj_error: float  # shrunk toward the field average: (sum err + k*mean) / (n + k), k=15
    mean_bias: float
    bias_label: str
    right_call_pct: float
    grade_538: str | None
    plus_minus_538: float | None
    methodology: str


def load_538() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = config.SEED_DIR / "fivethirtyeight"
    raw = pd.read_csv(d / "raw-polls-2023.csv", low_memory=False)
    ratings = pd.read_csv(d / "pollster-ratings-2023.csv")
    return raw, ratings


def _bias_label(b: float) -> str:
    if abs(b) < 0.3:
        return "±0.0"
    return f"D+{b:.1f}" if b > 0 else f"R+{abs(b):.1f}"


SHRINK_K = 15


def historical_scorecard(min_year: int = 2016, min_polls: int = 10) -> list[PollsterRow]:
    raw, ratings = load_538()
    sub = raw[(raw["year"] >= min_year) & raw["error"].notna()].copy()
    field_mean = float(sub["error"].mean())
    # one row per poll question is fine; 538 already de-duplicates per race
    grp = sub.groupby("pollster_rating_id")
    rat = ratings.set_index("Pollster Rating ID")
    rows: list[PollsterRow] = []
    for rid, g in grp:
        if len(g) < min_polls:
            continue
        name = g["pollster"].mode().iat[0]
        years = sorted(g["year"].unique())
        meth = g["methodology"].dropna().mode()
        r = rat.loc[rid] if rid in rat.index else None
        rows.append(PollsterRow(
            pollster=name,
            n_polls=int(len(g)),
            cycles=f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0]),
            mean_abs_error=round(float(g["error"].mean()), 1),
            adj_error=round((float(g["error"].sum()) + SHRINK_K * field_mean) / (len(g) + SHRINK_K), 2),
            mean_bias=round(float(g["bias"].dropna().mean()), 1) if g["bias"].notna().any() else 0.0,
            bias_label=_bias_label(float(g["bias"].dropna().mean())) if g["bias"].notna().any() else "n/a",
            right_call_pct=round(100 * float(g["rightcall"].mean()), 0),
            grade_538=str(r["538 Grade"]) if r is not None and pd.notna(r["538 Grade"]) else None,
            plus_minus_538=round(float(r["Predictive Plus-Minus"]), 2) if r is not None else None,
            methodology=str(meth.iat[0]) if len(meth) else "",
        ))
    # rank: lower error is better; tie-break by more polls
    rows.sort(key=lambda r: (r.adj_error, -r.n_polls))
    return rows


def cycle_scorecard(polls: pd.DataFrame, results: pd.DataFrame, window_days: int = 21) -> list[dict]:
    """Score polls against actual results for one cycle.

    polls: long-format polls (schema.POLL_COLUMNS) ; results: race_id, candidate, pct, election_date
    Only polls finishing within `window_days` before election day count (538 convention).
    """
    out: list[dict] = []
    if polls.empty or results.empty:
        return out
    results = results.copy()
    results["election_date"] = pd.to_datetime(results["election_date"]).dt.date
    for race_id, res in results.groupby("race_id"):
        eday = res["election_date"].iat[0]
        actual = dict(zip(res["candidate"], res["pct"]))
        cands = list(actual)[:2]
        if len(cands) < 2:
            continue
        p = polls[(polls["race_id"] == race_id) & (polls["end_date"] <= eday)
                  & (polls["end_date"] >= eday - timedelta(days=window_days))]
        if p.empty:
            continue
        wide = p.pivot_table(index=["poll_id", "pollster", "end_date"], columns="candidate", values="pct").reset_index()
        if not all(c in wide.columns for c in cands):
            continue
        actual_margin = actual[cands[0]] - actual[cands[1]]
        for _, row in wide.iterrows():
            poll_margin = row[cands[0]] - row[cands[1]]
            err = poll_margin - actual_margin
            out.append(dict(race_id=race_id, pollster=row["pollster"], end_date=row["end_date"],
                            poll_margin=round(poll_margin, 1), actual_margin=round(actual_margin, 1),
                            error=round(abs(err), 1), bias=round(err, 1),
                            right_call=(poll_margin > 0) == (actual_margin > 0)))
    return out
