"""Prediction-market snapshots from Polymarket (Gamma API).

The API is public and unauthenticated for read access. Prices are stored as
implied probabilities (0-100). We take one snapshot per run and keep history,
so the site can chart markets against the polling average over time.
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd
import requests

from . import config
from .schema import MARKET_COLUMNS, now_iso

log = logging.getLogger(__name__)
MIN_VOLUME = 10_000  # USD traded; thinner markets have prices nobody is trading at

# One spelling per candidate across platforms
OUTCOME_ALIASES = {"J.D. Vance": "JD Vance", "J. D. Vance": "JD Vance", "J.B. Pritzker": "JB Pritzker",
                   "J. B. Pritzker": "JB Pritzker", "Alexandria Ocasio Cortez": "Alexandria Ocasio-Cortez",
                   "AOC": "Alexandria Ocasio-Cortez", "RFK Jr.": "Robert F. Kennedy Jr."}


def canonical_outcome(name: str) -> str:
    name = " ".join(str(name).split())
    return OUTCOME_ALIASES.get(name, name)
POLY = "https://gamma-api.polymarket.com/events"
UA = f"ElectionsUSA-bot/1.0 (+{config.SITE['url']})"


def polymarket_event(slug: str, s: requests.Session) -> list[dict]:
    r = s.get(POLY, params={"slug": slug}, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    events = r.json()
    rows = []
    for ev in events if isinstance(events, list) else [events]:
        for m in ev.get("markets", []):
            # a closed, paused or barely traded contract keeps its last price forever (RFK Jr. sat at 49.0%
            # for days in November 2026); only live markets with real volume are recorded
            if m.get("closed") or m.get("active") is False or m.get("archived"):
                continue
            try:
                volume = float(m.get("volumeNum", m.get("volume")) or 0)
            except (TypeError, ValueError):
                volume = 0.0
            if volume < MIN_VOLUME:
                continue
            label = m.get("groupItemTitle") or m.get("question") or ""
            try:
                prices = json.loads(m.get("outcomePrices", "[]"))
                outcomes = json.loads(m.get("outcomes", "[]"))
            except (TypeError, json.JSONDecodeError):
                continue
            if "Yes" in outcomes and prices:
                yes = float(prices[outcomes.index("Yes")])
                rows.append((canonical_outcome(label), round(100 * yes, 1), f"https://polymarket.com/event/{slug}"))
    return rows


def fetch_all(session: requests.Session | None = None) -> pd.DataFrame:
    s = session or requests.Session()
    today = date.today().isoformat()
    out = []
    for mk in config.MARKETS:
        # Kalshi is linked, not republished: its terms for displaying prices are unclear
        for platform, fn, key in (("polymarket", polymarket_event, "polymarket_slug"),):
            ident = mk.get(key)
            if not ident:
                continue
            try:
                for outcome, price, url in fn(ident, s):
                    if price <= 0.5:  # skip dead long-shots to keep tables readable
                        continue
                    out.append(dict(snapshot_date=today, market_id=mk["id"], platform=platform, outcome=outcome,
                                    price=price, source_url=url, source_type="api", notes="", fetched_at=now_iso()))
            except Exception as e:
                log.warning("%s/%s: fetch failed: %s", mk["id"], platform, e)
    return pd.DataFrame(out, columns=MARKET_COLUMNS)
