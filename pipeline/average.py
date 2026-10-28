"""Transparent polling average.

Method (documented on /methodology/):
1. Recency: each poll is weighted 0.5 ** (age_in_days / half_life). The half-life
   is per race (14 days for fast-moving trackers, 30 days for early hypotheticals).
2. Sample size: weight * min(sqrt(n / 600), 1.5); unknown n is treated as 600.
3. Pollster quality: weight * grade_weight(538 2023 letter grade); unrated = 0.6.
4. Pollster frequency: a pollster that released k polls inside the active window
   has each of those polls divided by sqrt(k), so trackers cannot dominate.
5. Average = sum(w * pct) / sum(w) per candidate, over polls that asked about
   that candidate. Polls with weight below 1% of the top poll are excluded.

The trend line recomputes the same average as of each day in the past, using
only polls that had finished fieldwork by that day (no look-ahead).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from . import config


@dataclass
class RaceAverage:
    race_id: str
    as_of: date
    values: dict[str, float] = field(default_factory=dict)   # candidate -> avg
    n_polls: int = 0                                           # polls contributing meaningfully
    n_polls_total: int = 0
    trend: dict[str, list[tuple[date, float]]] = field(default_factory=dict)
    polls: pd.DataFrame | None = None                          # wide table of underlying polls
    margin: float | None = None                                # cand1 - cand2 for two-way races
    latest_end_date: date | None = None
    leader: str | None = None


def _grade_lookup(ratings: pd.DataFrame | None) -> dict[str, str]:
    if ratings is None or ratings.empty:
        return {}
    return {str(p).strip().lower(): str(g) for p, g in zip(ratings["Pollster"], ratings["538 Grade"])}


_GRADE_CACHE: dict[tuple[int, str], str | None] = {}


def pollster_grade(pollster: str, grades: dict[str, str]) -> str | None:
    key = pollster.strip().lower()
    ck = (id(grades), key)
    if ck in _GRADE_CACHE:
        return _GRADE_CACHE[ck]
    _GRADE_CACHE[ck] = g = _pollster_grade(key, grades)
    return g


def _pollster_grade(key: str, grades: dict[str, str]) -> str | None:
    if key in grades:
        return grades[key]
    # loose match: "Emerson College" vs "Emerson College Polling"
    for k, g in grades.items():
        if key in k or k in key:
            return g
    return None


def static_weights(wide: pd.DataFrame, grades: dict[str, str]) -> pd.Series:
    """Sample-size x pollster-quality factor; independent of the as-of date."""
    n = wide["sample_size"].fillna(600).clip(lower=50).astype(float)
    size = (n / 600.0).pow(0.5).clip(upper=1.5)
    quality = wide["pollster"].map(
        lambda p: config.GRADE_WEIGHTS.get(pollster_grade(p, grades) or "", config.DEFAULT_GRADE_WEIGHT)
    ).astype(float)
    return size * quality


def poll_weights(wide: pd.DataFrame, as_of: date, half_life: int, grades: dict[str, str],
                 static: pd.Series | None = None) -> pd.Series:
    """Compute a weight per poll row of a wide (one row per poll) frame."""
    if wide.empty:
        return pd.Series(dtype=float)
    if static is None:
        static = static_weights(wide, grades)
    age = (pd.Timestamp(as_of) - pd.to_datetime(wide["end_date"])).dt.days.clip(lower=0)
    recency = 0.5 ** (age / half_life)
    w = recency * static
    # frequency damping inside the active window (recency > 0.05)
    active = recency > 0.05
    counts = wide.loc[active, "pollster"].value_counts()
    damp = wide["pollster"].map(lambda p: 1 / math.sqrt(counts.get(p, 1)))
    return w * damp


def to_wide(polls: pd.DataFrame, race: config.Race) -> pd.DataFrame:
    """One row per poll, one column per candidate, plus poll metadata."""
    sub = polls[polls["race_id"] == race.id]
    if sub.empty:
        return pd.DataFrame()
    meta_cols = ["pollster", "sponsor", "start_date", "end_date", "sample_size", "population", "source_url", "notes"]
    meta = sub.drop_duplicates("poll_id").set_index("poll_id")[meta_cols]
    for c in ("sponsor", "notes", "source_url"):
        meta[c] = meta[c].fillna("").astype(str)
    vals = sub.pivot_table(index="poll_id", columns="candidate", values="pct", aggfunc="first")
    wide = meta.join(vals).reset_index()
    wide.columns.name = None
    for c in race.candidates:
        if c not in wide.columns:
            wide[c] = float("nan")
    return wide.sort_values("end_date", ascending=False).reset_index(drop=True)


def average_as_of(wide: pd.DataFrame, race: config.Race, as_of: date, grades: dict[str, str],
                  static: pd.Series | None = None) -> tuple[dict[str, float], int]:
    mask = wide["end_date"] <= as_of
    sub = wide[mask]
    if sub.empty:
        return {}, 0
    w = poll_weights(sub, as_of, race.half_life_days, grades, static[mask] if static is not None else None)
    if w.max() <= 0:
        return {}, 0
    keep = w >= 0.01 * w.max()
    sub, w = sub[keep], w[keep]
    # freshness: a candidate is shown only if at least one poll inside the active
    # window (recency weight > 0.05, i.e. ~4.3 half-lives) asked about them
    fresh_cutoff = as_of - timedelta(days=int(4.3 * race.half_life_days))
    fresh = sub["end_date"] >= fresh_cutoff
    out: dict[str, float] = {}
    for cand in race.candidates:
        vals = sub[cand]
        mask = vals.notna()
        if mask.sum() == 0 or not (mask & fresh).any():
            continue
        out[cand] = round(float((vals[mask] * w[mask]).sum() / w[mask].sum()), 1)
    return out, int(keep.sum())


def compute_race(polls: pd.DataFrame, race: config.Race, ratings: pd.DataFrame | None, as_of: date | None = None,
                 trend_step_days: int = 3) -> RaceAverage:
    as_of = as_of or date.today()
    grades = _grade_lookup(ratings)
    wide = to_wide(polls, race)
    ra = RaceAverage(race_id=race.id, as_of=as_of, polls=wide)
    if wide.empty:
        return ra
    ra.n_polls_total = len(wide)
    ra.latest_end_date = wide["end_date"].max()
    static = static_weights(wide, grades)
    ra.values, ra.n_polls = average_as_of(wide, race, as_of, grades, static)
    if ra.values:
        ra.leader = max(ra.values, key=ra.values.get)
        if race.kind in ("general", "generic", "approval") and len(race.candidates) >= 2:
            a, b = race.candidates[0], race.candidates[1]
            if a in ra.values and b in ra.values:
                ra.margin = round(ra.values[a] - ra.values[b], 1)
    # trend: from first poll end date (or as_of - 400d, whichever later) to as_of
    start = max(wide["end_date"].min(), as_of - timedelta(days=400))
    d = start
    series: dict[str, list[tuple[date, float]]] = {c: [] for c in race.candidates}
    while d <= as_of:
        vals, n = average_as_of(wide, race, d, grades, static)
        if n >= 1:
            for c, v in vals.items():
                series[c].append((d, v))
        d += timedelta(days=trend_step_days)
    if d - timedelta(days=trend_step_days) != as_of:
        vals, n = average_as_of(wide, race, as_of, grades, static)
        for c, v in vals.items():
            series[c].append((as_of, v))
    ra.trend = {c: s for c, s in series.items() if s}
    return ra
