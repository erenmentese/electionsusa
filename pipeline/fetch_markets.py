"""Prediction-market snapshots from Polymarket (Gamma API) and Kalshi (public API).

Both APIs are public and unauthenticated for read access. Prices are stored as
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
POLY = "https://gamma-api.polymarket.com/events"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"
UA = f"ElectionsUSA-bot/1.0 (+{config.SITE['url']})"


def polymarket_event(slug: str, s: requests.Session) -> list[dict]:
    r = s.get(POLY, params={"slug": slug}, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    events = r.json()
    rows = []
    for ev in events if isinstance(events, list) else [events]:
        for m in ev.get("markets", []):
            label = m.get("groupItemTitle") or m.get("question") or ""
            try:
                prices = json.loads(m.get("outcomePrices", "[]"))
                outcomes = json.loads(m.get("outcomes", "[]"))
            except (TypeError, json.JSONDecodeError):
                continue
            if "Yes" in outcomes and prices:
                yes = float(prices[outcomes.index("Yes")])
                rows.append((label.strip(), round(100 * yes, 1), f"https://polymarket.com/event/{slug}"))
    return rows


def kalshi_series(series_ticker: str, s: requests.Session) -> list[dict]:
    r = s.get(KALSHI, params={"series_ticker": series_ticker, "limit": 200, "status": "open"},
              headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    rows = []
    for m in r.json().get("markets", []):
        label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ""
        price = m.get("last_price")
        if price is None:
            bid, ask = m.get("yes_bid"), m.get("yes_ask")
            if bid is not None and ask is not None:
                price = (bid + ask) / 2
        if price is None:
            continue
        rows.append((label.strip(), round(float(price), 1), f"https://kalshi.com/markets/{series_ticker.lower()}"))
    return rows


def fetch_all(session: requests.Session | None = None) -> pd.DataFrame:
    s = session or requests.Session()
    today = date.today().isoformat()
    out = []
    for mk in config.MARKETS:
        for platform, fn, key in (("polymarket", polymarket_event, "polymarket_slug"),
                                  ("kalshi", kalshi_series, "kalshi_series")):
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
