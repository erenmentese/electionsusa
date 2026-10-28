"""Canonical long-format schema for polls and markets.

polls.csv: one row per (poll, candidate). Keeping the data long makes
multi-candidate primaries and two-way general-election matchups share the same
code path.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime

import pandas as pd

POLL_COLUMNS = [
    "poll_id",        # stable hash of race/pollster/end_date/population
    "race_id",        # key into config.RACES
    "pollster",       # canonical pollster name
    "sponsor",        # media sponsor, may be blank
    "start_date",     # ISO date
    "end_date",       # ISO date (used for recency weighting)
    "sample_size",    # int or blank
    "population",     # A (adults) | RV (registered voters) | LV (likely voters) | "" unknown
    "candidate",      # candidate / option label exactly as in config
    "pct",            # float, 0-100
    "source_url",     # where the number came from
    "source_type",    # seed | wikipedia | manual
    "notes",          # free text (e.g. "approximate, from press report")
    "fetched_at",     # ISO timestamp
]

MARKET_COLUMNS = [
    "snapshot_date",  # ISO date of the price observation
    "market_id",      # key into config.MARKETS
    "platform",       # polymarket | kalshi
    "outcome",        # candidate / option label
    "price",          # implied probability 0-100
    "source_url",
    "source_type",
    "notes",
    "fetched_at",
]


def make_poll_id(race_id: str, pollster: str, end_date: str, population: str = "") -> str:
    key = f"{race_id}|{pollster.strip().lower()}|{end_date}|{population}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def canonical_pollster(name: str) -> str:
    """Normalise pollster spellings so weights and scorecards line up."""
    n = re.sub(r"\s+", " ", str(name)).strip()
    n = re.sub(r"\[.*?\]", "", n).strip()  # strip Wikipedia footnote markers
    aliases = {
        "Emerson": "Emerson College",
        "Emerson College Polling": "Emerson College",
        "YouGov/Economist": "The Economist/YouGov",
        "Economist/YouGov": "The Economist/YouGov",
        "Ipsos/Reuters": "Reuters/Ipsos",
        "Quinnipiac": "Quinnipiac University",
        "Marist": "Marist College",
        "Siena/NYT": "The New York Times/Siena College",
        "New York Times/Siena College": "The New York Times/Siena College",
        "NYT/Siena": "The New York Times/Siena College",
        "Fox News/Beacon Research/Shaw & Co.": "Fox News",
        "Fox News/Beacon Research/Shaw & Co. Research": "Fox News",
        "Rasmussen": "Rasmussen Reports",
        "Pew": "Pew Research Center",
        "Pew Research": "Pew Research Center",
        "ABC/Washington Post/Ipsos": "ABC News/Washington Post/Ipsos",
        "ABC News/Washington Post": "ABC News/Washington Post/Ipsos",
        "Big Data Poll": "Big Data Poll",
    }
    return aliases.get(n, n)


def empty_polls() -> pd.DataFrame:
    return pd.DataFrame(columns=POLL_COLUMNS)


def empty_markets() -> pd.DataFrame:
    return pd.DataFrame(columns=MARKET_COLUMNS)


def validate_polls(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce types, drop unusable rows, return a clean copy."""
    df = df.copy()
    for c in POLL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[POLL_COLUMNS]
    df["pct"] = pd.to_numeric(df["pct"], errors="coerce")
    df["sample_size"] = pd.to_numeric(df["sample_size"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce").dt.date
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.date
    df = df.dropna(subset=["pct", "end_date", "race_id", "pollster", "candidate"])
    df = df[(df["pct"] >= 0) & (df["pct"] <= 100)]
    df["pollster"] = df["pollster"].map(canonical_pollster)
    df["population"] = df["population"].fillna("").astype(str).str.upper().str.strip()
    df = df.drop_duplicates(subset=["race_id", "pollster", "end_date", "population", "candidate"], keep="last")
    return df.reset_index(drop=True)


def today_iso() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
